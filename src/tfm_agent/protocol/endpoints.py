"""Discover live Transformice server endpoints from /proc (no hardcoded IPs)."""

from __future__ import annotations

import glob
import os
import socket
import struct
from dataclasses import dataclass
from pathlib import Path

from tfm_agent.steam.proton import find_game_processes, find_proton_processes

# Game ports observed: main 11801, satellite/world 13801 (range matches caseus).
GAME_PORT_RANGE = range(11800, 14900)
HTTP_PORTS = {80, 443, 10801}


@dataclass(frozen=True, slots=True)
class Endpoint:
    ip: str
    port: int
    proto: str  # tcp | udp

    @property
    def is_game_port(self) -> bool:
        return self.port in GAME_PORT_RANGE

    @property
    def key(self) -> tuple[str, int, str]:
        return (self.ip, self.port, self.proto)


def _decode_ip(ip_hex: str, ipv6: bool) -> str:
    if ipv6:
        raw = bytes.fromhex(ip_hex)
        words = [raw[i : i + 4][::-1] for i in range(0, 16, 4)]
        return socket.inet_ntop(socket.AF_INET6, b"".join(words))
    return socket.inet_ntoa(struct.pack("<I", int(ip_hex, 16)))


def _socket_inodes(pids: list[int]) -> set[str]:
    inodes: set[str] = set()
    for pid in pids:
        for fd in glob.glob(f"/proc/{pid}/fd/*"):
            try:
                link = os.readlink(fd)
            except OSError:
                continue
            if link.startswith("socket:["):
                inodes.add(link[8:-1])
    return inodes


def transformice_pids() -> list[int]:
    """PIDs whose cmdline looks like Transformice.exe or wineserver (wine shares fds)."""
    pids: list[int] = []
    for proc in find_game_processes():
        pids.append(proc.pid)
    for proc in find_proton_processes():
        if "wineserver" in proc.cmdline and proc.pid not in pids:
            pids.append(proc.pid)
    return pids


def discover_endpoints(pids: list[int] | None = None) -> list[Endpoint]:
    """Return non-loopback remote endpoints for sockets owned by `pids`."""
    if pids is None:
        pids = transformice_pids()
    if not pids:
        return []
    own = _socket_inodes(pids)
    if not own:
        return []

    found: list[Endpoint] = []
    seen: set[tuple[str, int, str]] = set()
    tables = (
        ("/proc/net/tcp", False, "tcp"),
        ("/proc/net/tcp6", True, "tcp"),
        ("/proc/net/udp", False, "udp"),
        ("/proc/net/udp6", True, "udp"),
    )
    for path, ipv6, proto in tables:
        try:
            with open(path, encoding="ascii") as handle:
                next(handle, None)
                for line in handle:
                    parts = line.split()
                    if len(parts) < 10:
                        continue
                    inode = parts[9]
                    state = parts[3]
                    if inode not in own:
                        continue
                    if proto == "tcp" and state != "01":
                        continue
                    rem = parts[2]
                    addr_hex, port_hex = rem.split(":")
                    ip = _decode_ip(addr_hex, ipv6)
                    port = int(port_hex, 16)
                    if ip.startswith(("127.", "::1")):
                        continue
                    key = (ip, port, proto)
                    if key in seen:
                        continue
                    seen.add(key)
                    found.append(Endpoint(ip=ip, port=port, proto=proto))
        except FileNotFoundError:
            continue
    return found


def game_endpoints(endpoints: list[Endpoint] | None = None) -> list[Endpoint]:
    """TCP endpoints on the Transformice game port range."""
    items = endpoints if endpoints is not None else discover_endpoints()
    return [e for e in items if e.proto == "tcp" and e.is_game_port]


def classify(endpoints: list[Endpoint]) -> dict[str, list[Endpoint]]:
    return {
        "game": [e for e in endpoints if e.proto == "tcp" and e.is_game_port],
        "http": [e for e in endpoints if e.port in HTTP_PORTS],
        "other": [
            e
            for e in endpoints
            if e.proto == "tcp" and e.port not in HTTP_PORTS and not e.is_game_port
        ],
        "udp": [e for e in endpoints if e.proto == "udp"],
    }


def endpoints_to_sniffer_targets(endpoints: list[Endpoint]) -> dict[str, object]:
    """Group game endpoints into caseus Sniffer main/satellite slots.

    Main = lowest game port (11801 typically). Satellite = other game
    endpoints (own IP and ports). Ports are never mixed across slots.
    """
    games = sorted(
        (e for e in endpoints if e.proto == "tcp" and e.is_game_port),
        key=lambda e: e.port,
    )
    if not games:
        return {"main": None, "satellite": None}
    main = games[0]
    others = games[1:]
    # All endpoints sharing main's IP stay on main (port rotation on same host).
    main_ports = sorted({e.port for e in games if e.ip == main.ip})
    sat_ip = None
    sat_ports: list[int] = []
    for e in others:
        if e.ip != main.ip:
            sat_ip = e.ip
            sat_ports.append(e.port)
    # If no distinct satellite IP, keep extra ports on main only.
    return {
        "main": {"ip": main.ip, "ports": main_ports},
        "satellite": (
            {"ip": sat_ip, "ports": sorted(set(sat_ports))} if sat_ip else None
        ),
    }


def steam_overlay_paths() -> list[Path]:
    home = Path.home()
    return [
        home / ".steam" / "steam" / "steamapps" / "common" / "Transformice",
        home / ".local" / "share" / "Steam" / "steamapps" / "common" / "Transformice",
    ]
