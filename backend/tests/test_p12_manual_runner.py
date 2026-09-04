"""P12 Runner 的 import、TTY 与本地 scripted driver 契约。"""

from types import SimpleNamespace

import pytest

from scripts import run_p12_real_readonly_acceptance as runner
from scripts.check_p12_real_readonly_preflight import (
    CREDENTIAL_REF_ENV,
    OPT_IN_ENV,
    OPT_IN_VALUE,
    SERVICE_ID_ENV,
    SERVICE_KIND_ENV,
    TARGET_CLASS_ENV,
    PreflightSafeStop,
)
from scripts.run_p12_real_readonly_acceptance import DeterministicLocalDriver, run_acceptance


def _environment() -> dict[str, str]:
    return {
        OPT_IN_ENV: OPT_IN_VALUE,
        SERVICE_ID_ENV: "redis.test",
        SERVICE_KIND_ENV: "redis",
        CREDENTIAL_REF_ENV: "registry:redis.test",
        TARGET_CLASS_ENV: "non-production",
    }


def test_runner_stops_before_runtime_import_without_tty() -> None:
    with pytest.raises(PreflightSafeStop) as captured:
        run_acceptance(_environment(), stdin=SimpleNamespace(isatty=lambda: False))
    assert captured.value.code == "P12_TTY_REQUIRED"


def test_scripted_driver_selects_only_registered_tool_then_finishes() -> None:
    driver = DeterministicLocalDriver("redis_health_overview")
    tools = [{"function": {"name": "redis_health_overview"}}]
    first = driver.chat([], tools=tools)
    second = driver.chat(
        [
            {
                "role": "tool",
                "content": (
                    '{"availability":"healthy","memory_bytes":128,"client_connections":2,'
                    '"slowlog_count":0,"observed_at":"2026-09-04T00:00:00+00:00",'
                    '"source_status":"available"}'
                ),
            }
        ],
        tools=tools,
    )
    assert first["tool_calls"][0]["function"] == {
        "name": "redis_health_overview",
        "arguments": "{}",
    }
    assert second["content"].startswith("只读健康事实：")
    assert "memory_bytes" in second["content"]


def test_scripted_driver_selects_postgres_health_not_first_legacy_tool() -> None:
    driver = DeterministicLocalDriver("check_connection_pool")
    tools = [
        {"function": {"name": "explain_sql"}},
        {"function": {"name": "check_connection_pool"}},
    ]
    first = driver.chat([], tools=tools)
    assert first["tool_calls"][0]["function"] == {
        "name": "check_connection_pool",
        "arguments": "{}",
    }


def test_scripted_driver_rejects_malformed_or_extra_service_fact() -> None:
    driver = DeterministicLocalDriver("redis_health_overview")
    tools = [{"function": {"name": "redis_health_overview"}}]
    driver.chat([], tools=tools)
    with pytest.raises(PreflightSafeStop, match="P12_TOOL_FACT_MALFORMED"):
        driver.chat(
            [{"role": "tool", "content": '{"availability":"healthy","key":"secret"}'}],
            tools=tools,
        )


def test_runner_maps_unexpected_exception_without_leaking_text(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(runner, "run_acceptance", lambda: (_ for _ in ()).throw(RuntimeError("secret-dsn")))
    assert runner.main() == 3
    output = capsys.readouterr()
    assert output.out.strip() == "P12 acceptance stopped: P12_RUNTIME_FAILED"
    assert output.err == ""
    assert "secret-dsn" not in output.out
