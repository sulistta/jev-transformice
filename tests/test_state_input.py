from __future__ import annotations

import pytest

from tfm_agent.input.mock import MockInputBackend
from tfm_agent.state.derived import estimate_velocity, vertical_state
from tfm_agent.state.raw import InputState


@pytest.mark.asyncio
async def test_mock_set_and_release() -> None:
    backend = MockInputBackend()
    await backend.set_state(InputState(left=True, jump=True))
    assert backend.current.left is True
    assert backend.current.jump is True
    await backend.release_all()
    assert backend.current == InputState()
    assert backend.release_count == 1


def test_estimate_velocity_ok() -> None:
    vx, vy = estimate_velocity(0.0, 0.0, 10.0, -5.0, 0.1)
    assert vx == pytest.approx(100.0)
    assert vy == pytest.approx(-50.0)


def test_estimate_velocity_bad_dt() -> None:
    assert estimate_velocity(0, 0, 1, 1, 0) is None
    assert estimate_velocity(0, 0, 1, 1, 10) is None


def test_vertical_state_y_down() -> None:
    ascending, falling = vertical_state(-3.0, y_down=True)
    assert ascending is True and falling is False
    ascending, falling = vertical_state(3.0, y_down=True)
    assert ascending is False and falling is True
    assert vertical_state(None) == (None, None)
