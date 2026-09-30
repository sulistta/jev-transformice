"""Environment capability report for Transformice observation/control."""

from __future__ import annotations

import os
import shutil
import socket
import sys
from dataclasses import dataclass, field
from pathlib import Path

from tfm_agent.steam import detect
from tfm_agent.steam import proton as proton_mod


@dataclass(frozen=True, slots=True)
class CheckResult:
    label: str
    status: str  # ok | missing | blocked | unknown | info
    detail: str
    remedy: str | None = None


@dataclass(slots=True)
class DoctorReport:
    checks: list[CheckResult] = field(default_factory=list)

    def add(
        self,
        label: str,
        status: str,
        detail: str,
        remedy: str | None = None,
    ) -> None:
        self.checks.append(CheckResult(label, status, detail, remedy))

    @property
    def ready_for_observation(self) -> bool:
        blocked = {"missing", "blocked"}
        required_labels = {"Transformice running", "Protocol observer"}
        for check in self.checks:
            if check.label in required_labels and check.status in blocked:
                return False
        return any(c.label == "Transformice running" and c.status == "ok" for c in self.checks)


def _os_release() -> str:
    path = Path("/etc/os-release")
    if not path.is_file():
        return sys.platform
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            data[key] = value.strip().strip('"')
    name = data.get("PRETTY_NAME") or data.get("NAME") or "unknown"
    return name


def _display_info() -> tuple[str, str]:
    session = os.environ.get("XDG_SESSION_TYPE", "unknown")
    display = os.environ.get("DISPLAY") or ""
    wayland = os.environ.get("WAYLAND_DISPLAY") or ""
    parts = [session]
    if display:
        parts.append(f"X11 DISPLAY={display}")
    if wayland:
        parts.append(f"WAYLAND_DISPLAY={wayland}")
    return session, ", ".join(parts)


def _check_capture_capability() -> CheckResult:
    python = Path(sys.executable).resolve()
    try:
        sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(0x0003))
    except PermissionError:
        return CheckResult(
            "Protocol observer",
            "blocked",
            f"raw socket denied for {python.name}",
            remedy=(
                f'sudo setcap cap_net_raw,cap_net_admin+eip "$(readlink -f "{python}")"'
            ),
        )
    except OSError as exc:
        return CheckResult(
            "Protocol observer",
            "blocked",
            f"raw socket unavailable: {exc}",
            remedy=(
                f'sudo setcap cap_net_raw,cap_net_admin+eip "$(readlink -f "{python}")"'
            ),
        )
    else:
        sock.close()
        return CheckResult("Protocol observer", "ok", "AF_PACKET raw socket allowed")


def _check_caseus() -> CheckResult:
    try:
        import caseus  # noqa: F401
    except ImportError:
        return CheckResult(
            "caseus",
            "missing",
            "not importable",
            remedy="uv sync --extra observe",
        )
    return CheckResult("caseus", "ok", "importable")


def _check_scapy() -> CheckResult:
    try:
        import scapy  # noqa: F401
    except ImportError:
        return CheckResult(
            "scapy",
            "missing",
            "not importable",
            remedy="uv sync --extra observe",
        )
    return CheckResult("scapy", "ok", "importable")


def _check_xdotool() -> CheckResult:
    path = shutil.which("xdotool")
    if path is None:
        return CheckResult(
            "Input x11 (xdotool)",
            "missing",
            "xdotool not on PATH",
            remedy="sudo apt install xdotool",
        )
    return CheckResult("Input x11 (xdotool)", "ok", path)


def _check_ydotool() -> CheckResult:
    path = shutil.which("ydotool")
    uinput = Path("/dev/uinput")
    if path is None:
        return CheckResult("Input wayland (ydotool)", "missing", "ydotool not on PATH")
    if uinput.exists():
        writable = os.access(uinput, os.W_OK)
        if not writable:
            return CheckResult(
                "Input wayland (ydotool)",
                "blocked",
                f"{uinput} not writable (permissions)",
                remedy="sudo usermod -aG input $USER  # then re-login",
            )
    return CheckResult("Input wayland (ydotool)", "ok", path)


def _check_window() -> CheckResult:
    xdotool = shutil.which("xdotool")
    if xdotool is None:
        return CheckResult("Game window", "unknown", "xdotool unavailable")
    import subprocess

    try:
        proc = subprocess.run(
            [xdotool, "search", "--name", "Transformice"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CheckResult("Game window", "unknown", f"search failed: {exc}")
    ids = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if not ids:
        return CheckResult(
            "Game window",
            "missing",
            "no window matching 'Transformice'",
            remedy="launch Transformice from Steam",
        )
    detail = f"{len(ids)} window(s): {', '.join(ids[:4])}"
    return CheckResult("Game window", "ok", detail)


def collect_report() -> DoctorReport:
    report = DoctorReport()

    report.add("OS", "info", _os_release())
    session, display_detail = _display_info()
    report.add("Display", "info", display_detail, remedy=None if session != "unknown" else None)

    steam = detect.find_steam()
    if steam is None:
        report.add(
            "Steam",
            "missing",
            "no steamapps directory found",
            remedy="set TFM_AGENT_STEAM_ROOT or install Steam",
        )
    else:
        report.add("Steam", "ok", str(steam.root))
        tools = proton_mod.installed_proton_tools(steam.root)
        if tools:
            report.add("Proton tools", "info", ", ".join(tools))

    install = detect.find_transformice(steam)
    if install is None:
        report.add(
            "Transformice installed",
            "missing",
            f"no appmanifest_{detect.TRANSFORMICE_APP_ID}.acf",
            remedy="install Transformice via Steam",
        )
    else:
        binary = detect.transformice_binary(install)
        status = "ok" if binary else "missing"
        detail = str(install.install_dir)
        report.add("Transformice installed", status, detail)
        compat = detect.compatdata_dir(install.steam, install.app_id)
        if compat:
            report.add("Compat data", "info", str(compat))

    games = proton_mod.find_game_processes()
    if games:
        primary = proton_mod.primary_game_process() or games[0]
        pids = ", ".join(str(p.pid) for p in games[:5])
        report.add("Transformice running", "ok", f"pid(s) {pids}")
        versions = proton_mod.proton_versions_in_use()
        if versions:
            report.add("Proton (running)", "info", ", ".join(versions))
        else:
            report.add("Proton (running)", "unknown", "no proton marker on cmdline")
    else:
        report.add(
            "Transformice running",
            "missing",
            "no Transformice.exe process",
            remedy="launch Transformice from Steam",
        )

    window = _check_window()
    report.add(window.label, window.status, window.detail, window.remedy)

    report.add(*_as_args(_check_xdotool()))
    report.add(*_as_args(_check_ydotool()))

    report.add(*_as_args(_check_caseus()))
    report.add(*_as_args(_check_scapy()))
    capture = _check_capture_capability()
    report.add(capture.label, capture.status, capture.detail, capture.remedy)

    return report


def _as_args(check: CheckResult) -> tuple[str, str, str, str | None]:
    return (check.label, check.status, check.detail, check.remedy)


def format_report(report: DoctorReport) -> str:
    width = max((len(c.label) for c in report.checks), default=10)
    lines = ["Transformice Jev Doctor", "=" * 40]
    for check in report.checks:
        lines.append(f"{check.label:<{width}}  {check.status:<8}  {check.detail}")
        if check.remedy and check.status in {"missing", "blocked"}:
            lines.append(f"{'':<{width}}  remedy:   {check.remedy}")
    lines.append("=" * 40)
    if report.ready_for_observation:
        lines.append("Status: ready for observation")
    else:
        lines.append("Status: not ready — apply remedies above")
    return "\n".join(lines)
