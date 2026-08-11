"""凭据的加密、掩码与主密钥封装（P6 API Key 与 P8 服务 DSN 共用）。

凭据安全边界（对齐 docs/开发规范.md 与 P6/P8 Design）：
- 明文凭据（API Key / DSN）绝不落库、绝不进日志 / Trace / 事件 / 接口响应。
- 主密钥来自环境变量 ``OPERMIND_SECRET_KEY``（>=32 字符），绝不落库/落代码/进日志。
- 主密钥丢失即密文不可解：由应用层降级为未配置，不伪造。
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MIN_SECRET_KEY_LENGTH = 32
MIN_API_KEY_LENGTH = 8
_NONCE_BYTES = 12
_API_KEY_INFO = b"opermind-model-provider-key-v1"
_DSN_INFO = b"opermind-service-dsn-v1"


class SecretKeyNotConfiguredError(Exception):
    """加密主密钥未配置，禁止保存凭据。"""


class SecretKeyTooShortError(Exception):
    """加密主密钥长度不足，无法安全派生密钥。"""


def load_secret_key() -> bytes:
    """从 ``OPERMIND_SECRET_KEY`` 派生 32 字节 AES-256 密钥（API Key 命名空间）。

    未配置或长度不足时抛错，由应用层转成诚实错误，不返回任何密钥内容。
    返回的密钥兼容 P6 既有 API Key 密文；DSN 加密在 encrypt_dsn 内另按 DSN
    命名空间派生，避免两套凭据密文可互换。
    """
    secret = os.environ.get("OPERMIND_SECRET_KEY", "")
    if not secret:
        raise SecretKeyNotConfiguredError("加密主密钥未配置，请设置 OPERMIND_SECRET_KEY。")
    if len(secret) < MIN_SECRET_KEY_LENGTH:
        raise SecretKeyTooShortError(
            f"OPERMIND_SECRET_KEY 长度不足，至少需要 {MIN_SECRET_KEY_LENGTH} 字符。"
        )
    return _derive_key(secret, _API_KEY_INFO)


def encrypt_api_key(plaintext: str, key: bytes) -> tuple[str, str]:
    """AES-256-GCM 加密模型 Provider API Key，返回 (Base64 密文, Base64 nonce)。"""
    return encrypt_secret(plaintext, key)


def decrypt_api_key(ciphertext_b64: str, nonce_b64: str, key: bytes) -> str:
    """解密模型 Provider API Key 密文；认证失败时抛错，绝不返回部分明文。"""
    return decrypt_secret(ciphertext_b64, nonce_b64, key)


def encrypt_dsn(plaintext: str, key: bytes) -> tuple[str, str]:
    """AES-256-GCM 加密服务 DSN，返回 (Base64 密文, Base64 nonce)。

    在传入主密钥基础上按 DSN 命名空间再派生实际 AES key，与 API Key 密文
    使用不同的 key-info，避免同主密钥下两套凭据密文可互换。
    """
    return encrypt_secret(plaintext, _derive_key_bytes(key, _DSN_INFO))


def decrypt_dsn(ciphertext_b64: str, nonce_b64: str, key: bytes) -> str:
    """解密服务 DSN 密文；认证失败时抛错，绝不返回部分明文。"""
    return decrypt_secret(ciphertext_b64, nonce_b64, _derive_key_bytes(key, _DSN_INFO))


def encrypt_secret(plaintext: str, key: bytes) -> tuple[str, str]:
    """AES-256-GCM 加密明文，返回 (Base64 密文, Base64 nonce)。"""
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return (
        base64.b64encode(ciphertext).decode("ascii"),
        base64.b64encode(nonce).decode("ascii"),
    )


def decrypt_secret(ciphertext_b64: str, nonce_b64: str, key: bytes) -> str:
    """解密 Base64 密文；认证失败时抛错，绝不返回部分明文。"""
    ciphertext = base64.b64decode(ciphertext_b64)
    nonce = base64.b64decode(nonce_b64)
    return AESGCM(key).decrypt(nonce, ciphertext, None).decode("utf-8")


def _derive_key(secret: str, info: bytes) -> bytes:
    """经 HKDF-SHA256 派生 32 字节密钥；主密钥本身已是高熵口令。"""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=info,
    ).derive(secret.encode("utf-8"))


def _derive_key_bytes(material: bytes, info: bytes) -> bytes:
    """从已有密钥材料按命名空间派生 32 字节子密钥（用于 DSN 与 API Key 隔离）。"""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=info,
    ).derive(material)
