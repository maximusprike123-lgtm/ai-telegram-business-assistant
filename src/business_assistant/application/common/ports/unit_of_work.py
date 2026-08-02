"""Atomic transaction boundary for consequential application use cases."""

from types import TracebackType
from typing import Protocol, Self


class UnitOfWork(Protocol):
    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None:
        """Commit staged aggregates, audit records, and events once."""
        ...

    async def rollback(self) -> None:
        """Discard all staged changes."""
        ...
