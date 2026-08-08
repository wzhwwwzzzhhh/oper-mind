"""P6 模型 Provider API Key 的加密、掩码与主密钥封装。

凭据安全边界（对齐 docs/开发规范.md 与 docs/design/model/P6模型Provider与APIKey管理Design.md D1）：
- 明文 API Key 绝不落库、绝不进日志 / Trace / 事件 / 接口响应。
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
_KEY_INFO = b"opermind-model-provider-key-v1"


class SecretKeyNotConfiguredError(Exception):
    """加密主密钥未配置，禁止保存 API Key。"""


class SecretKeyTooShortError(Exception):
    """加密主密钥长度不足，无法安全派生密钥。"""


def load_secret_key() -> bytes:
    """从 ``OPERMIND_SECRET_KEY`` 派生 32 字节 AES-256 密钥。

    未配置或长度不足时抛错，由应用层转成诚实错误，不返回任何密钥内容。
    """
    secret = os.environ.get("OPERMIND_SECRET_KEY", "")
    if not secret:
        raise SecretKeyNotConfiguredError("加密主密钥未配置，请设置 OPERMIND_SECRET_KEY。")
    if len(secret) < MIN_SECRET_KEY_LENGTH:
        raise SecretKeyTooShortError(
            f"OPERMIND_SECRET_KEY 长度不足，至少需要 {MIN_SECRET_KEY_LENGTH} 字符。"
        )
    return _derive_key(secret)


def encrypt_api_key(plaintext: str, key: bytes) -> tuple[str, str]:
    """AES-256-GCM 加密明文，返回 (Base64 密文, Base64 nonce)。"""
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return (
        base64.b64encode(ciphertext).decode("ascii"),
        base64.b64encode(nonce).decode("ascii"),
    )


def decrypt_api_key(ciphertext_b64: str, nonce_b64: str, key: bytes) -> str:
    """解密 Base64 密文；认证失败时抛错，绝不返回部分明文。"""
    ciphertext = base64.b64decode(ciphertext_b64)
    nonce = base64.b64decode(nonce_b64)
    return AESGCM(key).decrypt(nonce, ciphertext, None).decode("utf-8")


def _derive_key(secret: str) -> bytes:
    """经 HKDF-SHA256 派生 32 字节密钥；主密钥本身已是高熵口令。"""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_KEY_INFO,
    ).derive(secret.encode("utf-8"))
