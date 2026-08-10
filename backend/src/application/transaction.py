"""应用层共享事务助手：为短生命周期 Session 统一控制事务边界。"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.orm import Session

SessionFactory = Callable[[], Session]

TransactionT = TypeVar("TransactionT")


def in_transaction(session_factory: SessionFactory, operation: Callable[[Session], TransactionT]) -> TransactionT:
    """创建短生命周期 Session，提交成功则 commit，异常回滚后重抛。"""
    session = session_factory()
    try:
        result = operation(session)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
