"""Mock input backend for tests and dry runs."""

from __future__ import annotations

from tfm_agent.state.raw import InputState


class MockInputBackend:
    name = "mock"

    def __init__(self) -> None:
        self.current = InputState()
        self.history: list[InputState] = []
        self.release_count = 0

    async def set_state(self, state: InputState) -> None:
        self.current = state
        self.history.append(state)

    async def release_all(self) -> None:
        self.current = InputState()
        self.history.append(self.current)
        self.release_count += 1
