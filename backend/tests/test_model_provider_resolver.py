"""P6 模型 Provider 生效配置解析测试（不触发真实 LLM/网络）。"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import sessionmaker

from src.application.model_providers import resolve_model_config
from src.domain.model_provider import ModelProviderData, ProviderEndpoint
from src.infrastructure.persistence.database import Base
from src.infrastructure.persistence.model_provider_repository import SqlAlchemyModelProviderRepository
from src.infrastructure.secrets import encrypt_api_key, load_secret_key

MASTER_MATERIAL = "test-secret-key-0123456789abcdef0123456789abcdef"
PLAINTEXT_VALUE = "sk-test-provider-secret-1234"


@pytest.fixture
def session_factory(monkeypatch: pytest.MonkeyPatch, tmp_path) -> sessionmaker:
    """以 mock env 与临时 SQLite 构建应用层会话工厂。"""
    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://env-base")
    monkeypatch.setenv("OPERMIND_MODEL", "env-model")
    monkeypatch.setenv("OPERMIND_SECRET_KEY", MASTER_MATERIAL)
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{tmp_path / 'resolver.sqlite3'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _add_active_provider(sf: sessionmaker, *, with_key: bool) -> None:
    """写入并激活一个诊断端点的 Provider。"""
    encrypted, nonce = None, None
    if with_key:
        encrypted, nonce = encrypt_api_key(PLAINTEXT_VALUE, load_secret_key())
    with sf() as session:
        repository = SqlAlchemyModelProviderRepository(session)
        created = repository.add(
            ModelProviderData(
                name="P",
                base_url="https://api.p.com/v1",
                model="p-model",
                api_key_encrypted=encrypted,
                api_key_nonce=nonce,
                has_api_key=with_key,
            )
        )
        repository.activate(created.id, ProviderEndpoint.DIAGNOSTIC)
        session.commit()


def test_无激活Provider时回退envYAML(session_factory: sessionmaker) -> None:
    """无激活 Provider 时生效配置应来自 env/YAML。"""
    config = resolve_model_config(session_factory, load_secret_key())
    assert config["llm"]["api_key"] == "mock"
    assert config["llm"]["base_url"] == "http://env-base"
    assert config["llm"]["model"] == "env-model"


def test_激活Provider优先于env(session_factory: sessionmaker) -> None:
    """激活且带 Key 的 Provider 应覆盖 env/YAML。"""
    _add_active_provider(session_factory, with_key=True)
    config = resolve_model_config(session_factory, load_secret_key())
    assert config["llm"]["api_key"] == PLAINTEXT_VALUE
    assert config["llm"]["base_url"] == "https://api.p.com/v1"
    assert config["llm"]["model"] == "p-model"


def test_无Key的激活Provider不覆盖env(session_factory: sessionmaker) -> None:
    """激活但无 Key 的 Provider 无法连接，应回退 env/YAML（诚实降级）。"""
    _add_active_provider(session_factory, with_key=False)
    config = resolve_model_config(session_factory, load_secret_key())
    assert config["llm"]["api_key"] == "mock"
    assert config["llm"]["base_url"] == "http://env-base"


def test_主密钥缺失时激活Provider不覆盖env(session_factory: sessionmaker, monkeypatch: pytest.MonkeyPatch) -> None:
    """主密钥缺失时无法解密 DB Key，应回退 env/YAML。"""
    _add_active_provider(session_factory, with_key=True)
    monkeypatch.delenv("OPERMIND_SECRET_KEY", raising=False)
    config = resolve_model_config(session_factory, None)
    assert config["llm"]["api_key"] == "mock"


def test_应用库不可用时不抛错回退env(session_factory: sessionmaker) -> None:
    """应用库无表/连接失败时解析层不应崩溃，应回退 env/YAML。"""
    from sqlalchemy import create_engine

    broken_factory = sessionmaker(bind=create_engine("sqlite://"))
    # 空内存库没有 model_providers 表 → SQLAlchemyError → 回退 env
    config = resolve_model_config(broken_factory, load_secret_key())
    assert config["llm"]["api_key"] == "mock"
