"""Discover Steam installations and the Transformice app without hardcoded user paths."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

TRANSFORMICE_APP_ID = "335240"
TRANSFORMICE_NAME = "Transformice"


@dataclass(frozen=True, slots=True)
class SteamInstall:
    root: Path
    steamapps: Path

    @property
    def library_folders(self) -> list[Path]:
        return [self.steamapps]


@dataclass(frozen=True, slots=True)
class TransformiceInstall:
    steam: SteamInstall
    app_id: str
    install_dir: Path
    appmanifest: Path
    acf_name: str | None
    proton_hint: str | None = None


def candidate_steam_roots() -> list[Path]:
    seen: list[Path] = []
    env_root = os.environ.get("TFM_AGENT_STEAM_ROOT")
    if env_root:
        seen.append(Path(env_root).expanduser())
    steam_dir = os.environ.get("STEAM_DIR")
    if steam_dir:
        seen.append(Path(steam_dir).expanduser())
    home = Path.home()
    for rel in (
        ".steam/steam",
        ".steam/root",
        ".local/share/Steam",
        ".local/share/steam",
    ):
        seen.append(home / rel)
    unique: list[Path] = []
    for path in seen:
        resolved = path if not path.exists() else path.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def find_steam_roots() -> list[SteamInstall]:
    installs: list[SteamInstall] = []
    for root in candidate_steam_roots():
        steamapps = root / "steamapps"
        if steamapps.is_dir():
            installs.append(SteamInstall(root=root, steamapps=steamapps))
    return installs


def find_steam() -> SteamInstall | None:
    installs = find_steam_roots()
    return installs[0] if installs else None


def _parse_acf(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for key in ("appid", "name", "installdir", "StateFlags", "buildid"):
        match = re.search(rf'"{re.escape(key)}"\s+"([^"]*)"', text)
        if match:
            fields[key] = match.group(1)
    return fields


def find_transformice(steam: SteamInstall | None = None) -> TransformiceInstall | None:
    roots = [steam] if steam is not None else find_steam_roots()
    for install in roots:
        manifest = install.steamapps / f"appmanifest_{TRANSFORMICE_APP_ID}.acf"
        if not manifest.is_file():
            continue
        fields = _parse_acf(manifest.read_text(encoding="utf-8", errors="replace"))
        installdir = fields.get("installdir", TRANSFORMICE_NAME)
        install_dir = install.steamapps / "common" / installdir
        return TransformiceInstall(
            steam=install,
            app_id=fields.get("appid", TRANSFORMICE_APP_ID),
            install_dir=install_dir,
            appmanifest=manifest,
            acf_name=fields.get("name"),
        )
    return None


def transformice_binary(install: TransformiceInstall) -> Path | None:
    exe = install.install_dir / "Transformice.exe"
    return exe if exe.is_file() else None


def compatdata_dir(steam: SteamInstall, app_id: str = TRANSFORMICE_APP_ID) -> Path | None:
    path = steam.steamapps / "compatdata" / app_id
    return path if path.is_dir() else None
