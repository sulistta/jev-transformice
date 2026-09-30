"""Raw observation types — protocol truth only, no derived gameplay logic."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Vec2:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class InputState:
    left: bool = False
    right: bool = False
    jump: bool = False
    down: bool = False

    def as_tuple(self) -> tuple[bool, bool, bool, bool]:
        return (self.left, self.right, self.jump, self.down)


@dataclass(frozen=True, slots=True)
class PlayerState:
    player_id: int | None
    name: str | None
    position: Vec2 | None
    velocity: Vec2 | None
    dead: bool | None
    has_cheese: bool | None
    is_shaman: bool | None


@dataclass(frozen=True, slots=True)
class FieldAvailability:
    field: str
    available: bool
    source: str | None


@dataclass(frozen=True, slots=True)
class RawGameState:
    timestamp_monotonic: float
    map_code: str | None
    round_time: float | None
    self_player: PlayerState | None
    players: tuple[PlayerState, ...]
    observed_input: InputState | None
    map_xml: str | None
    availability: tuple[FieldAvailability, ...] = ()

    def availability_map(self) -> dict[str, FieldAvailability]:
        return {item.field: item for item in self.availability}
