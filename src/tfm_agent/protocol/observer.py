"""Live passive observation via caseus Sniffer with dynamic endpoints."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from tfm_agent.protocol.endpoints import (
    Endpoint,
    discover_endpoints,
    endpoints_to_sniffer_targets,
    game_endpoints,
)


@dataclass(slots=True)
class Observation:
    timestamp: float
    kind: str  # packet class name
    bound: str  # clientbound | serverbound
    fields: dict[str, Any] = field(default_factory=dict)
    raw_id: tuple[int, int] | None = None


@dataclass(slots=True)
class ObservationSummary:
    started_at: float
    endpoint: Endpoint | None
    counts: dict[str, int] = field(default_factory=dict)
    last: Observation | None = None
    self_position: tuple[float, float] | None = None
    self_velocity: tuple[float, float] | None = None
    self_session_id: int | None = None
    clientbound_self_xy: tuple[float, float] | None = None
    clientbound_self_v: tuple[float, float] | None = None
    has_keys: bool = False
    notes: list[str] = field(default_factory=list)

    def bump(self, kind: str) -> None:
        self.counts[kind] = self.counts.get(kind, 0) + 1


def _packet_fields(packet: object) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in dir(packet):
        if name.startswith("_"):
            continue
        if name in {"ctx", "id", "CIPHER", "RESERVED_FIELDS", "Header"}:
            continue
        try:
            value = getattr(packet, name)
        except Exception:
            continue
        if callable(value):
            continue
        out[name] = _jsonify(value)
    return out


def _jsonify(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, (int, float)):
        return value
    # fixedint / FixedInt and similar numeric wrappers
    if hasattr(value, "__int__") and type(value).__name__ in {
        "FixedInt",
        "UInt",
        "Int",
        "UnsignedInt",
        "UnsignedByte",
        "Byte",
        "UnsignedShort",
        "Short",
        "UInt8",
        "UInt32",
        "Int32",
    }:
        return int(value)
    if hasattr(value, "__float__") and not isinstance(value, (bytes, bytearray)):
        try:
            fv = float(value)
            if fv == fv:  # not NaN
                return fv
        except (TypeError, ValueError):
            pass
    if isinstance(value, (tuple, list)):
        return [_jsonify(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonify(v) for k, v in value.items()}
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    # Subpackets (friction_info, etc.)
    if hasattr(value, "__dict__") or hasattr(value, "field_names"):
        try:
            names = value.field_names()
            if callable(names):
                names = list(names)
            return {n: _jsonify(getattr(value, n)) for n in names}
        except Exception:
            pass
    return str(value)


def _patch_caseus_sniffer_decipher() -> None:
    """Fix caseus Sniffer serverbound decipher call (wrong kwargs in installed version)."""
    try:
        from caseus.packets import ServerboundPacket
        from caseus.sniffers import Sniffer
    except ImportError:
        return

    def _packet_from_data(self: Any, buf: Any) -> Any:
        header = ServerboundPacket.Header.unpack(buf, ctx=self.ctx)
        packet_cls = ServerboundPacket.subclass_with_id(header.id, ctx=self.ctx)
        if packet_cls is None:
            packet_cls = ServerboundPacket.GenericWithID(header.id)
        if self.secrets.packet_key_sources is not None:
            buf = packet_cls.decipher_data(
                buf, ctx=self.ctx, fingerprint=header.fingerprint
            )
        elif getattr(packet_cls, "CIPHER", None) is not None:
            packet_cls = ServerboundPacket.GenericWithID(header.id)
        return packet_cls.unpack_with_fingerprint(header.fingerprint, buf, ctx=self.ctx)

    Sniffer.ServerboundConnection._packet_from_data = _packet_from_data  # type: ignore[method-assign]


def build_sniffer(
    targets: dict[str, Any],
    packet_key_sources: list[int] | None = None,
    on_observation: Callable[[Observation, str], None] | None = None,
) -> Any:
    """Construct a caseus Sniffer bound to dynamic main/satellite targets."""
    _patch_caseus_sniffer_decipher()

    import pak
    from caseus.packets import clientbound, serverbound
    from caseus.secrets import Secrets
    from caseus.sniffers import Sniffer

    main = targets.get("main")
    if not main:
        raise RuntimeError("no game endpoint discovered — is Transformice running?")

    class LiveSniffer(Sniffer):
        def __init__(self) -> None:
            super().__init__()
            self.main.ip_addr = str(main["ip"])
            self.main.ports = list(main["ports"])
            sat = targets.get("satellite")
            if sat:
                self.satellite.ip_addr = str(sat["ip"])
                self.satellite.ports = list(sat["ports"])
            self._key_sources = packet_key_sources
            self.summary = ObservationSummary(
                started_at=time.time(),
                endpoint=Endpoint(
                    ip=str(main["ip"]),
                    port=int(main["ports"][0]),
                    proto="tcp",
                ),
                has_keys=bool(packet_key_sources),
            )

        async def startup(self) -> None:
            if self._key_sources:
                sec = Secrets(packet_key_sources=tuple(self._key_sources))
                for info in (self.main, self.satellite):
                    info.serverbound.secrets = sec
                    info.clientbound.secrets = sec
                self.summary.notes.append("packet_key_sources injected")
            else:
                self.summary.notes.append(
                    "no packet_key_sources — ciphered serverbound stay GenericWithID"
                )
            await super().startup()

        def _emit(self, bound: str, packet: object) -> None:
            obs = Observation(
                timestamp=time.time(),
                kind=type(packet).__name__,
                bound=bound,
                fields=_packet_fields(packet),
                raw_id=None,
            )
            self.summary.bump(f"{bound}:{obs.kind}")
            self.summary.last = obs
            if on_observation:
                on_observation(obs, bound)

        @pak.packet_listener(
            clientbound.NewRoundPacket,
            clientbound.SetRoundTimerPacket,
            clientbound.LoginSuccessPacket,
            clientbound.ChangeSatelliteServerPacket,
        )
        async def on_clientbound_named(self, server: Any, connection: Any, packet: Any) -> None:
            self._emit("clientbound", packet)
            if isinstance(packet, clientbound.LoginSuccessPacket):
                sid = getattr(packet, "session_id", None)
                if isinstance(sid, int):
                    self.summary.self_session_id = sid
                    self.summary.notes.append(f"self session_id={sid}")

        @pak.packet_listener(
            serverbound.GetCheesePacket,
            serverbound.EnterHolePacket,
            serverbound.PlayerDiedPacket,
            serverbound.HandshakePacket,
        )
        async def on_serverbound_keyless(self, server: Any, connection: Any, packet: Any) -> None:
            self._emit("serverbound", packet)

        @pak.packet_listener(clientbound.PlayerMovementPacket)
        async def on_clientbound_move(self, server: Any, connection: Any, packet: Any) -> None:
            self._emit("clientbound", packet)
            sid = getattr(packet, "session_id", None)
            try:
                xf, yf = float(packet.x), float(packet.y)
            except (TypeError, ValueError, AttributeError):
                return
            if self.summary.self_session_id is not None and sid == self.summary.self_session_id:
                self.summary.clientbound_self_xy = (xf, yf)
                try:
                    self.summary.clientbound_self_v = (
                        float(packet.velocity_x),
                        float(packet.velocity_y),
                    )
                except (TypeError, ValueError, AttributeError):
                    pass
                if self.summary.self_position is None:
                    self.summary.self_position = (xf, yf)
                    self.summary.notes.append("self x/y from clientbound echo")

        @pak.packet_listener(serverbound.PlayerMovementPacket)
        async def on_serverbound_move(self, server: Any, connection: Any, packet: Any) -> None:
            self._emit("serverbound", packet)
            x = getattr(packet, "x", None)
            y = getattr(packet, "y", None)
            try:
                xf, yf = float(x), float(y)
            except (TypeError, ValueError):
                return
            self.summary.self_position = (xf, yf)
            vx = getattr(packet, "velocity_x", None)
            vy = getattr(packet, "velocity_y", None)
            try:
                self.summary.self_velocity = (float(vx), float(vy))
            except (TypeError, ValueError):
                pass

        @pak.packet_listener(serverbound.KeyboardPacket)
        async def on_keyboard(self, server: Any, connection: Any, packet: Any) -> None:
            self._emit("serverbound", packet)

        @pak.packet_listener(pak.GenericPacket)
        async def on_generic(self, server: Any, connection: Any, packet: Any) -> None:
            bound = (
                "serverbound"
                if isinstance(connection, Sniffer.ServerboundConnection)
                else "clientbound"
            )
            raw_id = None
            try:
                raw_id = tuple(packet.id())  # type: ignore[call-arg]
            except Exception:
                pass
            obs = Observation(
                timestamp=time.time(),
                kind=type(packet).__name__,
                bound=bound,
                fields=_packet_fields(packet),
                raw_id=raw_id if isinstance(raw_id, tuple) else None,
            )
            label = f"{bound}:GenericWithID"
            self.summary.bump(label)
            if on_observation:
                on_observation(obs, bound)

    return LiveSniffer()


def live_targets() -> dict[str, Any]:
    endpoints = discover_endpoints()
    return endpoints_to_sniffer_targets(endpoints)


async def run_observe(
    *,
    duration_s: float | None = None,
    packet_key_sources: list[int] | None = None,
    json_mode: bool = False,
    endpoints: list[Endpoint] | None = None,
) -> int:
    """Run passive observation; print summary/availability matrix."""
    import asyncio
    import json
    import sys

    if endpoints is None:
        endpoints = discover_endpoints()
    games = game_endpoints(endpoints)
    if not games:
        print(
            "no game endpoints — launch Transformice and enter a room",
            file=sys.stderr,
        )
        return 1

    events: list[Observation] = []
    from tfm_agent.protocol.self_echo import SelfEchoTracker

    def on_phase(old: Any, new: Any) -> None:
        print(f"[self-echo] {old} -> {new}", file=sys.stderr, flush=True)

    tracker = SelfEchoTracker(min_echo_packets=5, on_phase=on_phase)

    def on_obs(obs: Observation, bound: str) -> None:
        events.append(obs)
        if obs.kind == "LoginSuccessPacket":
            sid = obs.fields.get("session_id")
            if isinstance(sid, int):
                tracker.on_login_success(sid)
        elif obs.kind == "PlayerMovementPacket" and bound == "clientbound":
            sid = obs.fields.get("session_id")
            x = obs.fields.get("x")
            y = obs.fields.get("y")
            vx = obs.fields.get("velocity_x")
            vy = obs.fields.get("velocity_y")
            if all(isinstance(v, (int, float)) for v in (sid, x, y, vx, vy)):
                tracker.on_movement(
                    session_id=int(sid),
                    t=obs.timestamp,
                    x=float(x),
                    y=float(y),
                    vx=float(vx),
                    vy=float(vy),
                )
                if tracker.latest_pose:
                    p = tracker.latest_pose
                    summary_note = sniffer.summary
                    summary_note.self_position = (p.x, p.y)
                    summary_note.self_velocity = (p.vx, p.vy)
                    summary_note.clientbound_self_xy = (p.x, p.y)
                    summary_note.clientbound_self_v = (p.vx, p.vy)
                    summary_note.self_session_id = tracker.session_id
                    if "self x/y from clientbound echo" not in summary_note.notes:
                        summary_note.notes.append("self x/y from clientbound echo")

        if json_mode:
            print(
                json.dumps(
                    {
                        "t": obs.timestamp,
                        "bound": bound,
                        "kind": obs.kind,
                        "fields": obs.fields,
                    },
                    default=str,
                ),
                flush=True,
            )
        else:
            keep = (
                "x",
                "y",
                "velocity_x",
                "velocity_y",
                "session_id",
                "map_code",
                "seconds",
                "username",
                "global_id",
            )
            brief = {k: obs.fields[k] for k in keep if k in obs.fields}
            if not brief:
                brief = {k: v for k, v in list(obs.fields.items())[:6]}
            print(f"[{bound}] {obs.kind} {brief}", flush=True)

    targets = endpoints_to_sniffer_targets(endpoints)
    sniffer = build_sniffer(
        targets,
        packet_key_sources=packet_key_sources,
        on_observation=on_obs,
    )

    print(
        f"observing main={targets['main']} satellite={targets['satellite']} "
        f"keys={'yes' if packet_key_sources else 'no'}",
        file=sys.stderr,
        flush=True,
    )
    print(
        "tip: to capture LoginSuccess/session_id, switch room or relog now; "
        "to capture cheese/hole/death events, play during this window",
        file=sys.stderr,
        flush=True,
    )

    try:
        await sniffer.startup()
    except PermissionError as exc:
        print(f"capture denied: {exc}", file=sys.stderr)
        return 1

    listen_task = asyncio.create_task(sniffer.listen())
    try:
        if duration_s is not None:
            await asyncio.sleep(duration_s)
        else:
            await asyncio.sleep(3600)
    finally:
        sniffer.close()
        listen_task.cancel()
        try:
            await listen_task
        except asyncio.CancelledError:
            pass

    summary = sniffer.summary
    # Merge self-echo tracker into summary for matrix
    if tracker.session_id is not None:
        summary.self_session_id = tracker.session_id
    if tracker.echo_count > 0:
        p = tracker.latest_pose
        if p is not None:
            summary.self_position = (p.x, p.y)
            summary.self_velocity = (p.vx, p.vy)
            summary.clientbound_self_xy = (p.x, p.y)
            summary.clientbound_self_v = (p.vx, p.vy)
            note = "self x/y from clientbound echo"
            if note not in summary.notes:
                summary.notes.append(note)
            summary.notes.append(
                f"self-echo phase={tracker.phase.value} packets={tracker.echo_count}"
            )
    print(_availability_matrix(summary, events), flush=True)
    return 0


def _availability_matrix(summary: ObservationSummary, events: list[Observation]) -> str:
    kinds = {e.kind for e in events}
    has_cb_xy = any(
        e.kind == "PlayerMovementPacket"
        and e.bound == "clientbound"
        and e.fields.get("x") is not None
        and e.fields.get("y") is not None
        for e in events
    )
    self_from_cb = summary.clientbound_self_xy is not None or summary.self_position is not None
    rows: list[tuple[str, bool, str]] = [
        ("map_code", "NewRoundPacket" in kinds, "clientbound NewRoundPacket"),
        ("round_time", "SetRoundTimerPacket" in kinds, "clientbound SetRoundTimerPacket"),
        (
            "session_id",
            summary.self_session_id is not None or "LoginSuccessPacket" in kinds,
            "clientbound LoginSuccessPacket",
        ),
        (
            "self_x_y",
            summary.self_position is not None,
            "serverbound PlayerMovementPacket (needs packet_key_sources)"
            if summary.self_position is None
            else (
                "clientbound PlayerMovement echo (session_id match)"
                if "self x/y from clientbound echo" in summary.notes
                else "serverbound PlayerMovementPacket"
            ),
        ),
        (
            "self_vx_vy",
            summary.self_velocity is not None or summary.clientbound_self_v is not None,
            "serverbound or clientbound PlayerMovementPacket",
        ),
        (
            "others_x_y",
            has_cb_xy,
            "clientbound PlayerMovementPacket",
        ),
        (
            "cheese_xy",
            "GetCheesePacket" in kinds,
            "serverbound GetCheesePacket (event)",
        ),
        (
            "hole_xy",
            "EnterHolePacket" in kinds,
            "serverbound EnterHolePacket (event)",
        ),
        (
            "death",
            "PlayerDiedPacket" in kinds,
            "serverbound PlayerDiedPacket (event)",
        ),
        (
            "keyboard",
            "KeyboardPacket" in kinds,
            "serverbound KeyboardPacket (needs keys + bindKeyboard)",
        ),
        (
            "other_players",
            "PlayerMovementPacket" in kinds
            and any(
                e.bound == "clientbound" and e.kind == "PlayerMovementPacket"
                for e in events
            ),
            "clientbound PlayerMovementPacket",
        ),
    ]
    lines = ["", "Availability matrix", "=" * 48]
    for name, ok, source in rows:
        status = "AVAILABLE" if ok else "UNAVAILABLE"
        lines.append(f"{name:<16} {status:<12} {source}")
    lines.append("=" * 48)
    lines.append(f"packets: {summary.counts}")
    lines.append(f"keys: {'yes' if summary.has_keys else 'no'}")
    for note in summary.notes:
        lines.append(f"note: {note}")
    return "\n".join(lines)
