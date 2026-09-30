"""Project configuration loading (TOML, env overrides)."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "default.toml"


@dataclass(frozen=True, slots=True)
class StateConfig:
    provider: str = "auto"


@dataclass(frozen=True, slots=True)
class InputConfig:
    backend: str = "auto"


@dataclass(frozen=True, slots=True)
class ObserverConfig:
    record: bool = False


@dataclass(frozen=True, slots=True)
class DecisionConfig:
    controller: str = "human"
    control_mode: str = "raw"
    max_state_age_ms: int = 300
    deadline_ms: int = 200
    fallback: str = "keep"


@dataclass(frozen=True, slots=True)
class ChunkedConfig:
    max_segments: int = 4
    max_horizon_ms: int = 350
    min_segment_ms: int = 20
    max_segment_ms: int = 200


@dataclass(frozen=True, slots=True)
class SafetyConfig:
    release_on_focus_loss: bool = True


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    level: str = "INFO"


@dataclass(frozen=True, slots=True)
class AppConfig:
    state: StateConfig = field(default_factory=StateConfig)
    input: InputConfig = field(default_factory=InputConfig)
    observer: ObserverConfig = field(default_factory=ObserverConfig)
    decision: DecisionConfig = field(default_factory=DecisionConfig)
    chunked: ChunkedConfig = field(default_factory=ChunkedConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    return value if isinstance(value, dict) else {}


def config_from_mapping(data: dict[str, Any]) -> AppConfig:
    decision_raw = _section(data, "decision")
    chunked_raw = _section(data, "chunked")
    return AppConfig(
        state=StateConfig(**_section(data, "state")),
        input=InputConfig(**_section(data, "input")),
        observer=ObserverConfig(**_section(data, "observer")),
        decision=DecisionConfig(
            controller=str(decision_raw.get("controller", "human")),
            control_mode=str(decision_raw.get("control_mode", "raw")),
            max_state_age_ms=int(decision_raw.get("max_state_age_ms", 300)),
            deadline_ms=int(decision_raw.get("deadline_ms", 200)),
            fallback=str(decision_raw.get("fallback", "keep")),
        ),
        chunked=ChunkedConfig(
            max_segments=int(chunked_raw.get("max_segments", 4)),
            max_horizon_ms=int(chunked_raw.get("max_horizon_ms", 350)),
            min_segment_ms=int(chunked_raw.get("min_segment_ms", 20)),
            max_segment_ms=int(chunked_raw.get("max_segment_ms", 200)),
        ),
        safety=SafetyConfig(**_section(data, "safety")),
        logging=LoggingConfig(**_section(data, "logging")),
    )


def load_config(path: Path | None = None) -> AppConfig:
    """Load TOML config; TFM_AGENT_CONFIG overrides path; missing file → defaults."""
    env_path = os.environ.get("TFM_AGENT_CONFIG")
    target = path or (Path(env_path) if env_path else DEFAULT_CONFIG_PATH)
    if not target.is_file():
        return AppConfig()
    with target.open("rb") as handle:
        data = tomllib.load(handle)
    return config_from_mapping(data)


def with_overrides(config: AppConfig, **decision_kwargs: Any) -> AppConfig:
    if not decision_kwargs:
        return config
    return replace(config, decision=replace(config.decision, **decision_kwargs))
