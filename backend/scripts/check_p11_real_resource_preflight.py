"""P11 真实资源验证的软件前门；本脚本自身绝不执行外部访问。"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass

OPT_IN_ENV = "OPERMIND_P11_REAL_TEST_OPT_IN"
TARGET_ENV = "OPERMIND_P11_REAL_TEST_TARGET_SERVICE_ID"
CREDENTIAL_REF_ENV = "OPERMIND_P11_REAL_TEST_CREDENTIAL_ENV"
OPT_IN_VALUE = "enabled"
_SERVICE_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


class PreflightSafeStop(Exception):
    """不携带目标或凭据正文的软件门拒绝。"""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


@dataclass(frozen=True)
class PreflightResult:
    """只表达技术前提，不表达人工授权或真实访问结果。"""

    technical_prerequisites: str = "satisfied"
    external_access_performed: bool = False
    human_authorization: str = "required"


def _credential_env_for(service_id: str) -> str:
    normalized = service_id.upper().replace("-", "_")
    return f"OPERMIND_SERVICE_{normalized}_DSN"


def check_preflight(environment: Mapping[str, str]) -> PreflightResult:
    """校验 opt-in、目标和凭据引用；不解析凭据，不调用任何访问函数。"""

    if environment.get(OPT_IN_ENV) != OPT_IN_VALUE:
        raise PreflightSafeStop("P11_REAL_TEST_OPT_IN_REQUIRED", "缺少显式真实测试 opt-in")

    target = environment.get(TARGET_ENV, "")
    if not _SERVICE_ID_RE.fullmatch(target):
        raise PreflightSafeStop("P11_REAL_TEST_TARGET_REQUIRED", "缺少合法的显式目标")

    credential_ref = environment.get(CREDENTIAL_REF_ENV, "")
    if not credential_ref:
        raise PreflightSafeStop(
            "P11_REAL_TEST_CREDENTIAL_REF_REQUIRED",
            "缺少凭据环境变量引用",
        )
    if credential_ref != _credential_env_for(target):
        raise PreflightSafeStop(
            "P11_REAL_TEST_CREDENTIAL_REF_MISMATCH",
            "凭据引用与显式目标不匹配",
        )
    if not environment.get(credential_ref, "").strip():
        raise PreflightSafeStop(
            "P11_REAL_TEST_CREDENTIAL_VALUE_REQUIRED",
            "凭据引用当前没有可用值",
        )

    return PreflightResult()


def main() -> int:
    """命令行只输出封闭状态；成功也不会开始真实测试。"""

    try:
        result = check_preflight(os.environ)
    except PreflightSafeStop as error:
        payload = {"status": "blocked", "code": error.code, "reason": error.reason}
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return 2
    sys.stdout.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
