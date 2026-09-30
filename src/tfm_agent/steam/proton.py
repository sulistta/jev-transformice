"""Locate running Transformice / Proton processes and parse Proton hints."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_PROTON_RE = re.compile(r"(GE-Proton[\w.-]*|UMU-Proton[\w.-]*|Proton[^/]*?)(?=/proton|$)")
_GAME_MARKERS = ("Transformice.exe", "transformice.exe")


@dataclass(frozen=True, slots=True)
class ProcessInfo:
    pid: int
    cmdline: str

    @property
    def exe_name(self) -> str:
        parts = self.cmdline.split("\x00") if "\x00" in self.cmdline else self.cmdline.split()
        if not parts:
            return ""
        return Path(parts[0]).name

    @property
    def proton_version(self) -> str | None:
        match = _PROTON_RE.search(self.cmdline)
        if not match:
            return None
        return match.group(1).strip().strip("'\"") or None


def _read_cmdline(pid: int) -> str | None:
    path = Path(f"/proc/{pid}/cmdline")
    try:
        raw = path.read_bytes()
    except (OSError, PermissionError):
        return None
    if not raw:
        return None
    return raw.decode("utf-8", errors="replace")


def iter_processes() -> list[ProcessInfo]:
    results: list[ProcessInfo] = []
    proc = Path("/proc")
    try:
        entries = list(proc.iterdir())
    except OSError:
        return results
    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        cmdline = _read_cmdline(pid)
        if cmdline is None:
            continue
        results.append(ProcessInfo(pid=pid, cmdline=cmdline.replace("\x00", " ").strip()))
    return results


def find_game_processes() -> list[ProcessInfo]:
    found: list[ProcessInfo] = []
    for proc in iter_processes():
        lowered = proc.cmdline.lower()
        if any(marker.lower() in lowered for marker in _GAME_MARKERS):
            found.append(proc)
    return found


def find_proton_processes() -> list[ProcessInfo]:
    found: list[ProcessInfo] = []
    for proc in iter_processes():
        lowered = proc.cmdline.lower()
        if "proton" in lowered or "wineserver" in lowered or "steam.exe" in lowered:
            found.append(proc)
    return found


def primary_game_process() -> ProcessInfo | None:
    games = find_game_processes()
    if not games:
        return None
    for proc in games:
        if "Transformice.exe" in proc.cmdline and not proc.cmdline.startswith("c:\\"):
            return proc
    return games[0]


def proton_versions_in_use() -> list[str]:
    versions: list[str] = []
    for proc in find_game_processes() + find_proton_processes():
        version = proc.proton_version
        if version and version not in versions:
            versions.append(version)
    return versions


def installed_proton_tools(steam_root: Path) -> list[str]:
    common = steam_root / "steamapps" / "common"
    if not common.is_dir():
        return []
    names: list[str] = []
    for path in sorted(common.iterdir()):
        name = path.name
        if name.startswith("Proton") or name.startswith("GE-Proton") or name.startswith("UMU-Proton"):
            names.append(name)
    return names
