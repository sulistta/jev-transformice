from __future__ import annotations

from pathlib import Path

from tfm_agent.steam import detect


def test_candidate_roots_include_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TFM_AGENT_STEAM_ROOT", str(tmp_path))
    roots = detect.candidate_steam_roots()
    assert tmp_path in [r.resolve() if r.exists() else r for r in roots] or tmp_path in roots


def test_find_steam_none_when_no_steamapps(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TFM_AGENT_STEAM_ROOT", str(tmp_path))
    monkeypatch.delenv("STEAM_DIR", raising=False)
    home = tmp_path / "empty-home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    steam = detect.find_steam()
    # env root has no steamapps → only home candidates, none with steamapps
    assert steam is None


def test_parse_acf_fields(tmp_path: Path, monkeypatch) -> None:
    steam_root = tmp_path / "steam"
    steamapps = steam_root / "steamapps"
    steamapps.mkdir(parents=True)
    (steamapps / "appmanifest_335240.acf").write_text(
        '"appid"\t\t"335240"\n'
        '\t"name"\t\t"Transformice"\n'
        '\t"installdir"\t\t"Transformice"\n'
        '\t"StateFlags"\t\t"4"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("TFM_AGENT_STEAM_ROOT", str(steam_root))
    monkeypatch.delenv("STEAM_DIR", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "no-home"))
    install = detect.find_transformice()
    assert install is not None
    assert install.app_id == "335240"
    assert install.install_dir == steamapps / "common" / "Transformice"
    assert detect.transformice_binary(install) is None  # exe not present in fixture
