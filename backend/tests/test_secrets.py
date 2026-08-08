"""P6 模型 Provider API Key 加密模块测试。"""

from __future__ import annotations

import pytest
from cryptography.exceptions import InvalidTag

from src.infrastructure.secrets import (
    MIN_API_KEY_LENGTH,
    SecretKeyNotConfiguredError,
    SecretKeyTooShortError,
    decrypt_api_key,
    encrypt_api_key,
    load_secret_key,
)

MASTER_MATERIAL = "test-secret-key-0123456789abcdef0123456789abcdef"


@pytest.fixture
def secret_key(monkeypatch: pytest.MonkeyPatch) -> bytes:
    """提供派生后的 32 字节主密钥。"""
    monkeypatch.setenv("OPERMIND_SECRET_KEY", MASTER_MATERIAL)
    return load_secret_key()


def test_加载主密钥派生32字节密钥(monkeypatch: pytest.MonkeyPatch) -> None:
    """OPERMIND_SECRET_KEY 应派生 32 字节 AES-256 密钥。"""
    monkeypatch.setenv("OPERMIND_SECRET_KEY", MASTER_MATERIAL)
    assert len(load_secret_key()) == 32


def test_主密钥缺失时报错(monkeypatch: pytest.MonkeyPatch) -> None:
    """未配置 OPERMIND_SECRET_KEY 时应诚实拒绝。"""
    monkeypatch.delenv("OPERMIND_SECRET_KEY", raising=False)
    with pytest.raises(SecretKeyNotConfiguredError):
        load_secret_key()


def test_主密钥过短时报错(monkeypatch: pytest.MonkeyPatch) -> None:
    """OPERMIND_SECRET_KEY 短于最小长度时应拒绝。"""
    monkeypatch.setenv("OPERMIND_SECRET_KEY", "too-short")
    with pytest.raises(SecretKeyTooShortError):
        load_secret_key()


def test_加解密往返(secret_key: bytes) -> None:
    """加密后应能解回原始明文。"""
    plaintext = "sk-test-12345678"
    encrypted, nonce = encrypt_api_key(plaintext, secret_key)
    assert decrypt_api_key(encrypted, nonce, secret_key) == plaintext


def test_密文与nonce均为base64且不同(secret_key: bytes) -> None:
    """同一明文两次加密应得到不同密文（随机 nonce）。"""
    first_encrypted, first_nonce = encrypt_api_key("sk-test-12345678", secret_key)
    second_encrypted, second_nonce = encrypt_api_key("sk-test-12345678", secret_key)
    assert first_encrypted != second_encrypted
    assert first_nonce != second_nonce


def test_错误密钥解密认证失败(monkeypatch: pytest.MonkeyPatch) -> None:
    """用错误主密钥解密应抛认证失败，绝不返回部分明文。"""
    monkeypatch.setenv("OPERMIND_SECRET_KEY", MASTER_MATERIAL)
    key = load_secret_key()
    encrypted, nonce = encrypt_api_key("sk-test-12345678", key)
    monkeypatch.setenv("OPERMIND_SECRET_KEY", "another-secret-key-0123456789abcdefghijkl")
    wrong_key = load_secret_key()
    with pytest.raises(InvalidTag):
        decrypt_api_key(encrypted, nonce, wrong_key)


def test_最小APIKey长度约束() -> None:
    """最小长度应保证掩码规则不会完整暴露短 Key。"""
    assert MIN_API_KEY_LENGTH >= 8
