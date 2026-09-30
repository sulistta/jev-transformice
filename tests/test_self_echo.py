from __future__ import annotations

from tfm_agent.protocol.self_echo import (
    SelfEchoPhase,
    SelfEchoTracker,
    PoseSample,
    compute_interval_metrics,
    correlate_hold,
    format_report,
    verify_association,
    SelfEchoReport,
    CorrelationResult,
)


def test_phase_progression() -> None:
    tr = SelfEchoTracker(min_echo_packets=3)
    assert tr.phase == SelfEchoPhase.WAITING_SESSION_ID
    tr.on_login_success(42)
    assert tr.phase == SelfEchoPhase.WAITING_SELF_ECHO
    assert tr.session_id == 42
    for i in range(3):
        assert tr.on_movement(
            session_id=42, t=1.0 + i, x=100 + i, y=50, vx=1, vy=0
        )
    assert tr.phase == SelfEchoPhase.SELF_ECHO_CONFIRMED
    tr.on_movement(session_id=42, t=5.0, x=110, y=50, vx=1, vy=0)
    assert tr.phase == SelfEchoPhase.OBSERVING_SELF
    assert tr.association_ready()


def test_rejects_wrong_session() -> None:
    tr = SelfEchoTracker(min_echo_packets=2)
    tr.on_login_success(42)
    assert tr.on_movement(session_id=99, t=1, x=0, y=0, vx=0, vy=0) is False
    assert tr.echo_count == 0


def test_relogin_resets_echo() -> None:
    tr = SelfEchoTracker(min_echo_packets=3)
    tr.on_login_success(1)
    tr.on_movement(session_id=1, t=1, x=0, y=0, vx=0, vy=0)
    tr.on_login_success(2)
    assert tr.session_id == 2
    assert tr.echo_count == 0
    assert tr.phase in (
        SelfEchoPhase.SESSION_IDENTIFIED,
        SelfEchoPhase.WAITING_SELF_ECHO,
    )


def test_interval_metrics() -> None:
    ts = [0.0, 0.02, 0.04, 0.06, 0.5]
    m = compute_interval_metrics(ts, duration_s=0.5)
    assert m is not None
    assert m.count == 5
    assert m.rate_hz > 0
    assert m.median_ms is not None and m.median_ms < 50
    assert m.gaps_over_100ms >= 1
    assert compute_interval_metrics([1.0]) is None


def _samples_right(n: int = 10) -> list[PoseSample]:
    return [
        PoseSample(t=100.0 + i * 0.02, x=100 + i * 10, y=50, vx=50, vy=0)
        for i in range(n)
    ]


def _samples_left(n: int = 10) -> list[PoseSample]:
    return [
        PoseSample(t=200.0 + i * 0.02, x=200 - i * 10, y=50, vx=-50, vy=0)
        for i in range(n)
    ]


def test_correlate_right_pass() -> None:
    s = _samples_right()
    r = correlate_hold(
        s, axis="x", hold_start=99, hold_end=101, min_travel=8, name="RIGHT", expected_sign=1
    )
    assert r.passed
    assert r.dx is not None and r.dx > 0


def test_correlate_left_pass() -> None:
    s = _samples_left()
    r = correlate_hold(
        s, axis="x", hold_start=199, hold_end=201, min_travel=8, name="LEFT", expected_sign=-1
    )
    assert r.passed
    assert r.dx is not None and r.dx < 0


def test_correlate_wrong_direction_fails() -> None:
    s = _samples_right()
    r = correlate_hold(
        s, axis="x", hold_start=99, hold_end=101, min_travel=8, name="LEFT", expected_sign=-1
    )
    assert not r.passed


def test_correlate_jump_y_down() -> None:
    samples = [
        PoseSample(t=300 + i * 0.02, x=10, y=200 - i * 15, vx=0, vy=-75)
        for i in range(8)
    ]
    r = correlate_hold(
        samples, axis="y", hold_start=299, hold_end=301, min_travel=3, name="JUMP", expected_sign=-1
    )
    assert r.passed


def test_verify_association_requires_both() -> None:
    ok_r = CorrelationResult("RIGHT", True, "ok")
    ok_l = CorrelationResult("LEFT", True, "ok")
    bad_l = CorrelationResult("LEFT", False, "bad")
    assert verify_association([ok_r, ok_l])
    assert not verify_association([ok_r, bad_l])
    assert not verify_association([ok_r])


def test_format_report_contains_sections() -> None:
    report = SelfEchoReport(
        phase=SelfEchoPhase.OBSERVING_SELF,
        login_success=True,
        session_id=7,
        echo_packets=10,
        duration_s=1.0,
        pose=PoseSample(t=1, x=1, y=2, vx=0, vy=0),
        has_xy=True,
        has_v=True,
        association_verified=True,
        metrics=None,
    )
    text = format_report(report)
    assert "SESSION" in text
    assert "SELF ECHO" in text
    assert "POSE" in text
    assert "self_x_y gate: PASS" in text
