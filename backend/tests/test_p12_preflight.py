"""P12 preflight 完全离线的失败关闭矩阵。"""

import pytest

from scripts.check_p12_real_readonly_preflight import (
    CREDENTIAL_REF_ENV,
    OPT_IN_ENV,
    OPT_IN_VALUE,
    SERVICE_ID_ENV,
    SERVICE_KIND_ENV,
    TARGET_CLASS_ENV,
    PreflightSafeStop,
    check_preflight,
)


def _valid() -> dict[str, str]:
    return {
        OPT_IN_ENV: OPT_IN_VALUE,
        SERVICE_ID_ENV: "1mysql.local_test",
        SERVICE_KIND_ENV: "mysql",
        CREDENTIAL_REF_ENV: "registry:1mysql.local_test",
        TARGET_CLASS_ENV: "non-production",
    }


def test_preflight_success_still_says_not_accessed() -> None:
    result = check_preflight(_valid())
    assert result.message == "技术前置满足、尚未访问"


@pytest.mark.parametrize(
    "key",
    [OPT_IN_ENV, SERVICE_ID_ENV, SERVICE_KIND_ENV, CREDENTIAL_REF_ENV, TARGET_CLASS_ENV],
)
def test_preflight_missing_requirement_fails_closed(key: str) -> None:
    environment = _valid()
    del environment[key]
    with pytest.raises(PreflightSafeStop):
        check_preflight(environment)


@pytest.mark.parametrize("value", ["", "Upper", "bad/value", "x" * 65])
def test_preflight_reuses_shared_service_id_validator(value: str) -> None:
    environment = _valid()
    environment[SERVICE_ID_ENV] = value
    with pytest.raises(PreflightSafeStop) as captured:
        check_preflight(environment)
    assert captured.value.code == "P12_SERVICE_ID_INVALID"


def test_preflight_rejects_ci_and_pytest_environment() -> None:
    for name in ("CI", "PYTEST_CURRENT_TEST"):
        environment = _valid()
        environment[name] = "1"
        with pytest.raises(PreflightSafeStop):
            check_preflight(environment)
