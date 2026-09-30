from __future__ import annotations

from pathlib import Path

from tfm_agent.config import config_from_mapping, load_config


def test_defaults_when_missing_file() -> None:
    cfg = load_config(Path("/nonexistent/tfm.toml"))
    assert cfg.decision.controller == "human"
    assert cfg.decision.fallback == "keep"
    assert cfg.decision.max_state_age_ms == 300
    assert cfg.chunked.max_segments == 4


def test_load_default_config() -> None:
    cfg = load_config()
    assert cfg.decision.control_mode == "raw"
    assert cfg.input.backend == "auto"


def test_config_from_mapping_typed() -> None:
    cfg = config_from_mapping(
        {
            "decision": {"controller": "jev", "deadline_ms": 150, "fallback": "release"},
            "chunked": {"max_horizon_ms": 250},
        }
    )
    assert cfg.decision.controller == "jev"
    assert cfg.decision.deadline_ms == 150
    assert cfg.decision.fallback == "release"
    assert cfg.chunked.max_horizon_ms == 250
