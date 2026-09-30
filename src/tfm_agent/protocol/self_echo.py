"""Self-pose resolution via LoginSuccess + clientbound movement echo.

State machine (explicit, no accidental association):

    WAITING_SESSION_ID
          ↓  LoginSuccess
    SESSION_IDENTIFIED
          ↓  N movement packets with matching session_id
    WAITING_SELF_ECHO → SELF_ECHO_CONFIRMED
          ↓  behavioral correlation (manual RIGHT/LEFT/JUMP)
    OBSERVING_SELF

session_id alone is never trusted: correlation must show the identified
player moves as the operator does across multiple transitions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from statistics import median
from typing import Callable, Sequence


class SelfEchoPhase(str, Enum):
    WAITING_SESSION_ID = "WAITING_SESSION_ID"
    SESSION_IDENTIFIED = "SESSION_IDENTIFIED"
    WAITING_SELF_ECHO = "WAITING_SELF_ECHO"
    SELF_ECHO_CONFIRMED = "SELF_ECHO_CONFIRMED"
    OBSERVING_SELF = "OBSERVING_SELF"


@dataclass(frozen=True, slots=True)
class PoseSample:
    t: float
    x: float
    y: float
    vx: float
    vy: float
    source: str = "clientbound_echo"
    session_id: int | None = None


@dataclass(slots=True)
class IntervalMetrics:
    count: int
    duration_s: float
    rate_hz: float
    median_ms: float | None
    p95_ms: float | None
    max_gap_ms: float | None
    gaps_over_100ms: int


@dataclass(slots=True)
class CorrelationResult:
    name: str  # RIGHT | LEFT | JUMP
    passed: bool
    detail: str
    dx: float | None = None
    dy: float | None = None
    max_abs_vx: float | None = None
    max_abs_vy: float | None = None
    latency_ms: float | None = None


@dataclass(slots=True)
class SelfEchoReport:
    phase: SelfEchoPhase
    login_success: bool
    session_id: int | None
    echo_packets: int
    duration_s: float
    pose: PoseSample | None
    has_xy: bool
    has_v: bool
    association_verified: bool
    metrics: IntervalMetrics | None
    correlations: list[CorrelationResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def gate_passed(self) -> bool:
        return (
            self.login_success
            and self.session_id is not None
            and self.echo_packets > 0
            and self.has_xy
            and self.association_verified
            and self.phase
            in (SelfEchoPhase.SELF_ECHO_CONFIRMED, SelfEchoPhase.OBSERVING_SELF)
        )


class SelfEchoTracker:
    """Pure state machine — feed LoginSuccess / movement observations."""

    def __init__(
        self,
        *,
        min_echo_packets: int = 5,
        on_phase: Callable[[SelfEchoPhase, SelfEchoPhase], None] | None = None,
    ) -> None:
        self.phase = SelfEchoPhase.WAITING_SESSION_ID
        self.session_id: int | None = None
        self.min_echo_packets = min_echo_packets
        self._on_phase = on_phase
        self._samples: list[PoseSample] = []
        self._login_seen = False
        self._echo_count = 0
        self._started = time.monotonic()
        self.notes: list[str] = []

    def _set_phase(self, new: SelfEchoPhase) -> None:
        if new == self.phase:
            return
        old = self.phase
        self.phase = new
        self.notes.append(f"{old.value} -> {new.value}")
        if self._on_phase:
            self._on_phase(old, new)

    def on_login_success(self, session_id: int) -> None:
        if session_id <= 0:
            return
        if self.session_id is not None and self.session_id != session_id:
            # Re-login during experiment: adopt new session, reset echo progress.
            self.notes.append(
                f"session_id changed {self.session_id} -> {session_id} (relogin)"
            )
            self._echo_count = 0
            self._samples.clear()
            self._set_phase(SelfEchoPhase.SESSION_IDENTIFIED)
        self.session_id = session_id
        self._login_seen = True
        if self.phase == SelfEchoPhase.WAITING_SESSION_ID:
            self._set_phase(SelfEchoPhase.SESSION_IDENTIFIED)
            self._set_phase(SelfEchoPhase.WAITING_SELF_ECHO)

    def on_movement(
        self,
        *,
        session_id: int,
        t: float,
        x: float,
        y: float,
        vx: float,
        vy: float,
    ) -> bool:
        """Return True if this packet is accepted as self-echo."""
        if self.session_id is None or session_id != self.session_id:
            return False
        sample = PoseSample(t=t, x=x, y=y, vx=vx, vy=vy, session_id=session_id)
        self._samples.append(sample)
        self._echo_count += 1
        if self.phase == SelfEchoPhase.WAITING_SELF_ECHO and self._echo_count >= self.min_echo_packets:
            self._set_phase(SelfEchoPhase.SELF_ECHO_CONFIRMED)
        elif self.phase == SelfEchoPhase.SELF_ECHO_CONFIRMED:
            self._set_phase(SelfEchoPhase.OBSERVING_SELF)
        return True

    @property
    def echo_count(self) -> int:
        return self._echo_count

    @property
    def samples(self) -> list[PoseSample]:
        return list(self._samples)

    @property
    def login_seen(self) -> bool:
        return self._login_seen

    @property
    def latest_pose(self) -> PoseSample | None:
        return self._samples[-1] if self._samples else None

    @property
    def duration_s(self) -> float:
        return max(time.monotonic() - self._started, 1e-9)

    def association_ready(self) -> bool:
        return self.phase in (
            SelfEchoPhase.SELF_ECHO_CONFIRMED,
            SelfEchoPhase.OBSERVING_SELF,
        )


def compute_interval_metrics(
    timestamps: Sequence[float],
    *,
    duration_s: float | None = None,
) -> IntervalMetrics | None:
    if len(timestamps) < 2:
        return None
    ts = sorted(timestamps)
    intervals = [b - a for a, b in zip(ts, ts[1:]) if b > a]
    if not intervals:
        return None
    dur = duration_s if duration_s is not None else (ts[-1] - ts[0])
    dur = max(dur, 1e-9)
    ms = [iv * 1000.0 for iv in intervals]
    ms_sorted = sorted(ms)
    p95 = ms_sorted[min(len(ms_sorted) - 1, int(round(0.95 * (len(ms_sorted) - 1))))]
    return IntervalMetrics(
        count=len(ts),
        duration_s=dur,
        rate_hz=len(ts) / dur,
        median_ms=median(ms),
        p95_ms=p95,
        max_gap_ms=max(ms),
        gaps_over_100ms=sum(1 for v in ms if v > 100.0),
    )


def correlate_hold(
    samples: Sequence[PoseSample],
    *,
    axis: str,
    hold_start: float,
    hold_end: float,
    min_travel: float = 5.0,
    name: str | None = None,
    expected_sign: int | None = None,
) -> CorrelationResult:
    """Validate pose change on an axis during a manual hold window.

    axis: 'x' or 'y'. expected_sign: +1 increasing, -1 decreasing.
    For JUMP use axis='y' and expected_sign=-1 (y-down: jump decreases y).
    """
    label = name or axis.upper()
    window = [s for s in samples if hold_start <= s.t <= hold_end]
    if len(window) < 2:
        return CorrelationResult(
            name=label,
            passed=False,
            detail=f"only {len(window)} samples in hold window",
        )
    first, last = window[0], window[-1]
    if axis == "x":
        delta = last.x - first.x
        max_abs_v = max(abs(s.vx) for s in window)
        max_abs_v2 = None
    else:
        delta = last.y - first.y
        max_abs_v = max(abs(s.vy) for s in window)
        max_abs_v2 = max(abs(s.vx) for s in window)
        max_abs_v, max_abs_v2 = max_abs_v, max_abs_v2

    sign = expected_sign if expected_sign is not None else (
        1 if axis == "x" else -1
    )
    # JUMP: expect y decrease (negative dy) when expected_sign=-1 on y
    if axis == "y" and label == "JUMP":
        # either clear upward motion (vy < 0) or y decreased
        passed = (delta < -min_travel) or (max_abs_v > 1.0 and delta < 0)
        detail = f"dy={delta:.2f} max|vy|={max_abs_v:.2f}"
        return CorrelationResult(
            name=label,
            passed=bool(passed),
            detail=detail,
            dx=None,
            dy=delta,
            max_abs_vx=max_abs_v2,
            max_abs_vy=max_abs_v,
        )

    passed = (delta * sign) >= min_travel
    # also accept sustained velocity in the expected direction
    if not passed and axis == "x":
        vx_samples = [s.vx for s in window]
        if sign > 0 and max(v for v in vx_samples if v is not None) > 1.0:
            if last.x > first.x:
                passed = True
        if sign < 0 and min(v for v in vx_samples if v is not None) < -1.0:
            if last.x < first.x:
                passed = True

    detail = f"d{axis}={delta:.2f} max|v|={max_abs_v:.2f} n={len(window)}"
    return CorrelationResult(
        name=label,
        passed=bool(passed),
        detail=detail,
        dx=delta if axis == "x" else None,
        dy=delta if axis == "y" else None,
        max_abs_vx=max_abs_v if axis == "x" else max_abs_v2,
        max_abs_vy=max_abs_v if axis == "y" else None,
    )


def verify_association(correlations: Sequence[CorrelationResult]) -> bool:
    """Behavioral gate: RIGHT and LEFT must both pass (transitions both ways)."""
    by_name = {c.name: c for c in correlations}
    right = by_name.get("RIGHT")
    left = by_name.get("LEFT")
    if right is None or left is None:
        return False
    return right.passed and left.passed


def format_report(report: SelfEchoReport) -> str:
    lines: list[str] = []
    lines.append("SESSION")
    lines.append(f"LoginSuccess observed: {'YES' if report.login_success else 'NO'}")
    lines.append(
        f"session_id: {'resolved' if report.session_id is not None else 'unresolved'}"
    )
    lines.append(f"phase: {report.phase.value}")
    lines.append("")
    lines.append("SELF ECHO")
    lines.append(f"movement packets: {report.echo_packets}")
    lines.append(f"duration: {report.duration_s:.1f}s")
    if report.metrics:
        m = report.metrics
        lines.append(f"rate: {m.rate_hz:.1f} Hz")
        lines.append(f"median interval: {m.median_ms:.1f} ms")
        lines.append(f"p95 interval: {m.p95_ms:.1f} ms")
        lines.append(f"max gap: {m.max_gap_ms:.1f} ms")
        lines.append(f"gaps>100ms: {m.gaps_over_100ms}")
    else:
        lines.append("rate: n/a (need ≥2 packets)")
    lines.append("")
    lines.append("POSE")
    lines.append(f"x/y: {'AVAILABLE' if report.has_xy else 'UNAVAILABLE'}")
    lines.append(f"vx/vy: {'AVAILABLE' if report.has_v else 'UNAVAILABLE'}")
    lines.append(
        "player association: "
        + ("VERIFIED" if report.association_verified else "UNVERIFIED")
    )
    if report.pose:
        p = report.pose
        lines.append(f"latest: x={p.x:.1f} y={p.y:.1f} vx={p.vx:.1f} vy={p.vy:.1f}")
        lines.append(f"source: {p.source}")
    lines.append("")
    if report.correlations:
        lines.append("CORRELATION")
        for c in report.correlations:
            status = "PASS" if c.passed else "FAIL"
            lines.append(f"manual {c.name}: {status}  ({c.detail})")
        lines.append("")
    lines.append("GATE")
    lines.append(f"self_x_y gate: {'PASS' if report.gate_passed else 'FAIL'}")
    if report.notes:
        lines.append("")
        lines.append("NOTES")
        for n in report.notes[-12:]:
            lines.append(f"- {n}")
    return "\n".join(lines)
