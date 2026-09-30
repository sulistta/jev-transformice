from __future__ import annotations

import pytest

from tfm_agent.cli import main


def test_version(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "tfm-agent" in out


def test_doctor_runs(capsys) -> None:
    code = main(["doctor"])
    out = capsys.readouterr().out
    assert "Transformice Jev Doctor" in out
    assert "Steam" in out
    assert code in (0, 1)


def test_observe_without_game_still_importable(capsys, monkeypatch) -> None:
    from tfm_agent.protocol import endpoints as ep

    monkeypatch.setattr(ep, "discover_endpoints", lambda: [])
    monkeypatch.setattr(
        "tfm_agent.cli.cmd_observe.__module__",
        "tfm_agent.cli",
    )
    # Force import path used inside cmd_observe
    monkeypatch.setattr(
        "tfm_agent.protocol.endpoints.discover_endpoints",
        lambda: [],
    )
    code = main(["observe", "--json"])
    captured = capsys.readouterr()
    # Either no_endpoints (1) or implementation still stubbing — never crash
    assert code in (0, 1, 2)
    assert "no game endpoints" in captured.err or "no_endpoints" in captured.out or "observe" in captured.err


def test_run_plans_controller(capsys) -> None:
    code = main(["run", "--controller", "jev", "--dry-run"])
    err = capsys.readouterr().err
    assert code == 2
    assert "controller=jev" in err
    assert "dry_run=True" in err


def test_experiment_unimplemented_gate(capsys) -> None:
    code = main(["experiment", "proxy-smoke-test"])
    assert code == 2
