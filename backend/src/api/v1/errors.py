"""P2.4 v1 API 的安全协议异常。"""

from __future__ import annotations


class ApiV1Error(Exception):
    """可映射为 P0.3 安全错误体的 API 协议异常。"""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
