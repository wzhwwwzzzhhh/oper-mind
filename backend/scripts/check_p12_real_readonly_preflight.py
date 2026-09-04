"""P12 真实只读验收的软件前门；本模块不导入任何网络 client。"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

from src.domain.services import validate_service_instance_id

OPT_IN_ENV = "OPERMIND_P12_REAL_OPT_IN"
SERVICE_ID_ENV = "OPERMIND_P12_SERVICE_ID"
SERVICE_KIND_ENV = "OPERMIND_P12_SERVICE_KIND"
CREDENTIAL_REF_ENV = "OPERMIND_P12_CREDENTIAL_REF"
TARGET_CLASS_ENV = "OPERMIND_P12_TARGET_CLASS"
OPT_IN_VALUE = "P12_REAL_READONLY_ACCEPTANCE"

_KINDS = frozenset({"postgres", "redis", "mysql"})
_ENV_REF = re.compile(r"env:[A-Z][A-Z0-9_]{0,127}$")


class PreflightSafeStop(RuntimeError):
    """不包含目标或 credential reference 的固定失败。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class PreflightResult:
    """技术前置安全投影；不表示已经获得人工授权。"""

    service_id: str
    kind: str
    credential_ref: str
    message: str = "技术前置满足、尚未访问"


def check_preflight(environment: Mapping[str, str]) -> PreflightResult:
    """验证声明字符串；不读取 credential value，也不访问任何外部目标。"""
    if environment.get("CI") or environment.get("PYTEST_CURRENT_TEST"):
        raise PreflightSafeStop("P12_INTERACTIVE_ENV_REQUIRED")
    if environment.get(OPT_IN_ENV) != OPT_IN_VALUE:
        raise PreflightSafeStop("P12_OPT_IN_REQUIRED")
    try:
        service_id = validate_service_instance_id(environment.get(SERVICE_ID_ENV, ""))
    except ValueError as error:
        raise PreflightSafeStop("P12_SERVICE_ID_INVALID") from error
    kind = environment.get(SERVICE_KIND_ENV, "").strip().lower()
    if kind not in _KINDS:
        raise PreflightSafeStop("P12_SERVICE_KIND_INVALID")
    if environment.get(TARGET_CLASS_ENV) != "non-production":
        raise PreflightSafeStop("P12_NON_PRODUCTION_REQUIRED")
    credential_ref = environment.get(CREDENTIAL_REF_ENV, "").strip()
    if credential_ref.startswith("registry:"):
        if credential_ref != f"registry:{service_id}":
            raise PreflightSafeStop("P12_CREDENTIAL_REF_MISMATCH")
    elif _ENV_REF.fullmatch(credential_ref) is None:
        raise PreflightSafeStop("P12_CREDENTIAL_REF_INVALID")
    return PreflightResult(service_id=service_id, kind=kind, credential_ref=credential_ref)


def main() -> int:
    """命令行只输出固定状态，不输出 target/ref/env name。"""
    try:
        result = check_preflight(os.environ)
    except PreflightSafeStop as error:
        print(f"P12 preflight failed: {error.code}")
        return 2
    print(result.message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
