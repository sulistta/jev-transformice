"""Input backend protocol — keys only, no game knowledge."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from tfm_agent.state.raw import InputState


@runtime_checkable
class InputBackend(Protocol):
    name: str

    async def set_state(self, state: InputState) -> None:
        """Apply the full key state (press/release as needed)."""
        ...

    async def release_all(self) -> None:
        """Release every key this backend may have pressed. Must be idempotent."""
        ...
