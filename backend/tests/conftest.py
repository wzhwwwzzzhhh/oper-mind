"""pytest 导入引导与全局状态隔离。"""

import atexit
import ipaddress
import os
import socket
import sys
import tempfile
from pathlib import Path
from threading import local
from typing import Any

_OFFLINE_TEMP_DIRECTORY = tempfile.TemporaryDirectory(prefix="opermind-p11-pytest-")
atexit.register(_OFFLINE_TEMP_DIRECTORY.cleanup)


def _configure_offline_environment() -> None:
    """在测试模块 collection 前压过所有已知真实资源配置入口。"""

    for name in tuple(os.environ):
        if name.startswith("OPERMIND_SERVICE_") and name.endswith(("_DSN", "_LOG_DIR")):
            os.environ.pop(name, None)
    offline_database = Path(_OFFLINE_TEMP_DIRECTORY.name) / "application.sqlite3"
    os.environ.update(
        {
            "OPERMIND_API_KEY": "mock",
            "OPERMIND_BASE_URL": "http://mock.invalid",
            "OPERMIND_MODEL": "mock",
            "OPERMIND_PG_DSN": "",
            "OPERMIND_KNOWLEDGE_DIR": "",
            "OPERMIND_APP_DATABASE_URL": f"sqlite:///{offline_database.as_posix()}",
        }
    )


_configure_offline_environment()

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
for path in (PROJECT_ROOT, BACKEND_ROOT):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)

import httpx
import pytest
import redis
from data.scenarios import clear_active_scenario
from sqlalchemy.engine import Engine

from src.project_paths import ensure_project_import_paths

ensure_project_import_paths()

_OFFLINE_ERROR = "OFFLINE_TEST_EXTERNAL_ACCESS_BLOCKED"
_ALLOWED_FILE_ROOTS: set[Path] = set()
_SOCKETPAIR_STATE = local()


def _blocked_external_access(*args: object, **kwargs: object) -> None:
    del args, kwargs
    raise RuntimeError(_OFFLINE_ERROR)


def _is_within_allowed_root(path: Path) -> bool:
    for root in _ALLOWED_FILE_ROOTS:
        try:
            path.resolve().relative_to(root)
        except (OSError, ValueError):
            continue
        return True
    return False


def _install_collection_time_blockers() -> pytest.MonkeyPatch:
    """在测试模块 collection 前安装全 session 离线拒绝器。"""

    patcher = pytest.MonkeyPatch()
    original_socket_connect = socket.socket.connect
    original_socketpair = socket.socketpair

    def guarded_create_connection(*args: object, **kwargs: object) -> Any:
        del args, kwargs
        _blocked_external_access()

    def guarded_getaddrinfo(host: object, *args: object, **kwargs: object) -> Any:
        del kwargs
        normalized = str(host)
        if normalized == "localhost":
            normalized = "127.0.0.1"
        try:
            address = ipaddress.ip_address(normalized)
        except ValueError:
            if normalized.endswith(".invalid"):
                raise socket.gaierror(socket.EAI_NONAME, "offline reserved domain") from None
            _blocked_external_access()
        port = args[0] if args else 0
        family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
        socket_address = (str(address), port, 0, 0) if address.version == 6 else (str(address), port)
        return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", socket_address)]

    def guarded_socket_connect(instance: socket.socket, address: object) -> None:
        if not getattr(_SOCKETPAIR_STATE, "active", False):
            _blocked_external_access()
        original_socket_connect(instance, address)  # type: ignore[arg-type]

    def guarded_socket_connect_ex(instance: socket.socket, address: object) -> int:
        del instance, address
        _blocked_external_access()
        raise AssertionError("unreachable")

    def guarded_socketpair(*args: object, **kwargs: object) -> tuple[socket.socket, socket.socket]:
        previous = getattr(_SOCKETPAIR_STATE, "active", False)
        _SOCKETPAIR_STATE.active = True
        try:
            return original_socketpair(*args, **kwargs)
        finally:
            _SOCKETPAIR_STATE.active = previous

    patcher.setattr(socket, "create_connection", guarded_create_connection)
    patcher.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    patcher.setattr(socket, "gethostbyname", _blocked_external_access)
    patcher.setattr(socket, "gethostbyname_ex", _blocked_external_access)
    patcher.setattr(socket, "gethostbyaddr", _blocked_external_access)
    patcher.setattr(socket, "getnameinfo", _blocked_external_access)
    patcher.setattr(socket.socket, "connect", guarded_socket_connect)
    patcher.setattr(socket.socket, "connect_ex", guarded_socket_connect_ex)
    patcher.setattr(socket.socket, "sendto", _blocked_external_access)
    if hasattr(socket.socket, "sendmsg"):
        patcher.setattr(socket.socket, "sendmsg", _blocked_external_access)
    patcher.setattr(socket, "socketpair", guarded_socketpair)
    patcher.setattr(redis.Redis, "execute_command", _blocked_external_access)
    patcher.setattr(httpx.HTTPTransport, "handle_request", _blocked_external_access)
    patcher.setattr(httpx.AsyncHTTPTransport, "handle_async_request", _blocked_external_access)

    original_engine_connect = Engine.connect

    def guarded_engine_connect(engine: Engine) -> Any:
        if engine.dialect.name != "sqlite":
            _blocked_external_access()
        return original_engine_connect(engine)

    patcher.setattr(Engine, "connect", guarded_engine_connect)

    from src.application.knowledge import KnowledgeReaderService
    from src.infrastructure.logs.log_source import LogSourceConnector
    from src.tools.knowledge_tools import SearchKnowledgeTool

    def require_test_directory(value: str | None) -> None:
        if value and not _is_within_allowed_root(Path(value)):
            _blocked_external_access()

    original_log_root = LogSourceConnector._resolve_root

    def guarded_log_root(connector: LogSourceConnector) -> Path | None:
        require_test_directory(connector._log_dir)
        return original_log_root(connector)

    original_knowledge_execute = SearchKnowledgeTool.execute

    def guarded_knowledge_execute(
        tool: SearchKnowledgeTool,
        query: str,
        limit: int = 5,
    ) -> str:
        require_test_directory(tool._directory)
        return original_knowledge_execute(tool, query, limit)

    original_service_root = KnowledgeReaderService.root.fget
    assert original_service_root is not None

    def guarded_service_root(service: KnowledgeReaderService) -> Path | None:
        require_test_directory(service._directory)
        return original_service_root(service)

    patcher.setattr(LogSourceConnector, "_resolve_root", guarded_log_root)
    patcher.setattr(SearchKnowledgeTool, "execute", guarded_knowledge_execute)
    patcher.setattr(KnowledgeReaderService, "root", property(guarded_service_root))
    return patcher


_COLLECTION_TIME_PATCHER = _install_collection_time_blockers()


@pytest.fixture(scope="session", autouse=True)
def _allow_pytest_temp_directory(tmp_path_factory: pytest.TempPathFactory) -> None:
    """仅允许 pytest 自身唯一临时根下的 deterministic 文件 fake。"""

    _ALLOWED_FILE_ROOTS.add(tmp_path_factory.getbasetemp().resolve())


@pytest.fixture(autouse=True)
def _clear_active_scenario():
    """每条用例后清除激活场景，避免模块级状态跨用例残留。"""
    yield
    clear_active_scenario()
