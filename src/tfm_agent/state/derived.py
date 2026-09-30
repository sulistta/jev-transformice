"""Derived features — always tagged with an explicit source."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Source = Literal["protocol", "finite_difference", "geometry", "inferred"]


@dataclass(frozen=True, slots=True)
class SourcedFloat:
    value: float | None
    source: Source | None


@dataclass(frozen=True, slots=True)
class SourcedBool:
    value: bool | None
    source: Source | None


@dataclass(frozen=True, slots=True)
class DerivedMotionState:
    estimated_vx: SourcedFloat
    estimated_vy: SourcedFloat
    ascending: SourcedBool
    falling: SourcedBool
    grounded: SourcedBool
    jump_available: SourcedBool
    left_contact: SourcedBool
    right_contact: SourcedBool


def estimate_velocity(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    dt: float,
) -> tuple[float, float] | None:
    """Finite-difference velocity using real timestamps; None if dt unusable."""
    if dt <= 0 or dt > 5.0:
        return None
    return ((x1 - x0) / dt, (y1 - y0) / dt)


def vertical_state(vy: float | None, *, y_down: bool = True) -> tuple[bool | None, bool | None]:
    """Return (ascending, falling) from vy. Screen y-down: positive vy = falling."""
    if vy is None:
        return None, None
    if y_down:
        return (vy < 0, vy > 0)
    return (vy > 0, vy < 0)
