"""Interactive self-echo experiment: LoginSuccess → echo → correlation → metrics."""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from typing import Any

from tfm_agent.protocol.endpoints import discover_endpoints, game_endpoints
from tfm_agent.protocol.observer import Observation, build_sniffer
from tfm_agent.protocol.self_echo import (
    CorrelationResult,
    SelfEchoPhase,
    SelfEchoReport,
    SelfEchoTracker,
    compute_interval_metrics,
    correlate_hold,
    format_report,
    verify_association,
)


def _prompt(msg: str, *, interactive: bool) -> None:
    print(msg, file=sys.stderr, flush=True)
    if interactive:
        try:
            input("  [Enter] when ready to measure… ")
        except EOFError:
            pass


async def run_self_echo(
    *,
    duration_s: float = 90.0,
    interactive: bool = True,
    skip_correlation: bool = False,
    min_echo_packets: int = 5,
    json_mode: bool = False,
) -> int:
    endpoints = discover_endpoints()
    if not game_endpoints(endpoints):
        print("self-echo: no game endpoints — start Transformice and join a room", file=sys.stderr)
        return 1

    from tfm_agent.protocol.endpoints import endpoints_to_sniffer_targets

    tracker = SelfEchoTracker(min_echo_packets=min_echo_packets)
    phase_log: list[str] = []

    def on_phase(old: SelfEchoPhase, new: SelfEchoPhase) -> None:
        phase_log.append(f"{old.value} -> {new.value}")
        print(f"[phase] {old.value} -> {new.value}", file=sys.stderr, flush=True)

    tracker._on_phase = on_phase  # type: ignore[attr-defined]
    # rebuild with callback
    tracker = SelfEchoTracker(min_echo_packets=min_echo_packets, on_phase=on_phase)

    correlations: list[CorrelationResult] = []
    other_last: dict[int, tuple[float, float]] = {}

    def on_obs(obs: Observation, bound: str) -> None:
        if obs.kind == "LoginSuccessPacket":
            sid = obs.fields.get("session_id")
            if isinstance(sid, int):
                tracker.on_login_success(sid)
                print(f"[session] LoginSuccess session_id={sid}", file=sys.stderr, flush=True)
            return
        if obs.kind != "PlayerMovementPacket" or bound != "clientbound":
            return
        sid = obs.fields.get("session_id")
        x = obs.fields.get("x")
        y = obs.fields.get("y")
        vx = obs.fields.get("velocity_x")
        vy = obs.fields.get("velocity_y")
        if not all(isinstance(v, (int, float)) for v in (sid, x, y, vx, vy)):
            return
        accepted = tracker.on_movement(
            session_id=int(sid),
            t=obs.timestamp,
            x=float(x),
            y=float(y),
            vx=float(vx),
            vy=float(vy),
        )
        if not accepted and tracker.session_id is not None:
            other_last[int(sid)] = (float(x), float(y))

    targets = endpoints_to_sniffer_targets(endpoints)
    sniffer = build_sniffer(targets, packet_key_sources=None, on_observation=on_obs)

    print(
        f"self-echo: observing main={targets['main']} sat={targets['satellite']} "
        f"duration={duration_s}s interactive={interactive}",
        file=sys.stderr,
        flush=True,
    )

    if interactive:
        print(
            "STEP 1/4 — WAITING_SESSION_ID: switch room or relog in Transformice now.",
            file=sys.stderr,
            flush=True,
        )

    try:
        await sniffer.startup()
    except PermissionError as exc:
        print(f"capture denied: {exc}", file=sys.stderr)
        return 1

    listen_task = asyncio.create_task(sniffer.listen())
    t0 = time.monotonic()
    try:
        # Phase A: wait for session + min echo (or timeout)
        deadline_session = t0 + min(duration_s, 45.0)
        while time.monotonic() < deadline_session:
            if tracker.association_ready():
                break
            await asyncio.sleep(0.2)
        else:
            if not tracker.login_seen:
                print(
                    "[warn] LoginSuccess not observed — stay on game, relog/switch room",
                    file=sys.stderr,
                )

        if tracker.session_id is not None and not tracker.association_ready():
            print(
                "STEP 2/4 — WAITING_SELF_ECHO: identified session, waiting for movement…",
                file=sys.stderr,
                flush=True,
            )
            deadline_echo = t0 + duration_s
            while time.monotonic() < deadline_echo and not tracker.association_ready():
                await asyncio.sleep(0.2)

        # Correlation windows
        if (
            interactive
            and not skip_correlation
            and tracker.association_ready()
            and tracker.latest_pose is not None
        ):
            prompts = (
                ("RIGHT", "STEP 3/4 — Hold RIGHT arrow for 3s (game focused)."),
                ("LEFT", "Hold LEFT arrow for 3s."),
                ("JUMP", "Press JUMP (space/up) once or twice."),
            )
            for name, msg in prompts:
                _prompt(msg + " Press Enter, then start holding immediately.", interactive=True)
                await asyncio.sleep(0.3)
                window_start = time.monotonic()
                # use wall timestamps from samples (time.time from observer)
                hold_start = time.time() - 0.3
                if name == "JUMP":
                    await asyncio.sleep(2.5)
                else:
                    await asyncio.sleep(3.0)
                hold_end = time.time()
                samples = tracker.samples
                if name == "JUMP":
                    result = correlate_hold(
                        samples,
                        axis="y",
                        hold_start=hold_start,
                        hold_end=hold_end,
                        min_travel=3.0,
                        name="JUMP",
                        expected_sign=-1,
                    )
                else:
                    result = correlate_hold(
                        samples,
                        axis="x",
                        hold_start=hold_start,
                        hold_end=hold_end,
                        min_travel=8.0,
                        name=name,
                        expected_sign=1 if name == "RIGHT" else -1,
                    )
                correlations.append(result)
                print(
                    f"[corr] {result.name}: "
                    + ("PASS" if result.passed else "FAIL")
                    + f" ({result.detail})",
                    file=sys.stderr,
                    flush=True,
                )
                await asyncio.sleep(0.5)

        # Collect until duration or enough post-correlation samples
        end = t0 + duration_s
        while time.monotonic() < end:
            await asyncio.sleep(0.2)

    finally:
        sniffer.close()
        listen_task.cancel()
        try:
            await listen_task
        except asyncio.CancelledError:
            pass

    samples = tracker.samples
    timestamps = [s.t for s in samples]
    metrics = compute_interval_metrics(timestamps, duration_s=tracker.duration_s)
    pose = tracker.latest_pose
    has_xy = pose is not None
    has_v = pose is not None

    if skip_correlation or not interactive:
        # Association provisional: echo count only — not behavioral
        association = tracker.association_ready() and not skip_correlation
        if skip_correlation:
            association = False
            print(
                "[note] correlation skipped — association UNVERIFIED",
                file=sys.stderr,
            )
    else:
        association = verify_association(correlations)
        if association and tracker.phase == SelfEchoPhase.SELF_ECHO_CONFIRMED:
            tracker._set_phase(SelfEchoPhase.OBSERVING_SELF)

    report = SelfEchoReport(
        phase=tracker.phase,
        login_success=tracker.login_seen,
        session_id=tracker.session_id,
        echo_packets=tracker.echo_count,
        duration_s=tracker.duration_s,
        pose=pose,
        has_xy=has_xy,
        has_v=has_v,
        association_verified=association,
        metrics=metrics,
        correlations=correlations,
        notes=list(tracker.notes) + list(phase_log),
    )

    if skip_correlation:
        report.notes.append(
            "partial: self pose stream live, association not behaviorally verified"
        )

    text = format_report(report)
    if json_mode:
        import json

        payload = {
            "phase": report.phase.value,
            "login_success": report.login_success,
            "session_id_resolved": report.session_id is not None,
            "echo_packets": report.echo_packets,
            "duration_s": report.duration_s,
            "rate_hz": report.metrics.rate_hz if report.metrics else None,
            "median_ms": report.metrics.median_ms if report.metrics else None,
            "p95_ms": report.metrics.p95_ms if report.metrics else None,
            "has_xy": report.has_xy,
            "has_v": report.has_v,
            "association_verified": report.association_verified,
            "correlations": [
                {"name": c.name, "passed": c.passed, "detail": c.detail}
                for c in report.correlations
            ],
            "gate_passed": report.gate_passed,
        }
        print(json.dumps(payload, indent=2))
    else:
        print(text)

    # Exit 0 if session+echo+xy at minimum (stream works); 0 full only if gate
    if report.login_success and report.echo_packets > 0 and report.has_xy:
        if report.association_verified or skip_correlation:
            return 0 if report.gate_passed or skip_correlation else 1
        return 1
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LoginSuccess + self-echo gate")
    parser.add_argument("--duration", type=float, default=90.0)
    parser.add_argument("--skip-correlation", action="store_true")
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--min-echo", type=int, default=5)
    args = parser.parse_args(argv)
    return asyncio.run(
        run_self_echo(
            duration_s=args.duration,
            interactive=not args.non_interactive,
            skip_correlation=args.skip_correlation,
            min_echo_packets=args.min_echo,
            json_mode=args.json,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
