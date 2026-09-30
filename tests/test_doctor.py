from __future__ import annotations

from tfm_agent.doctor import DoctorReport, collect_report, format_report


def test_collect_report_has_core_checks() -> None:
    report = collect_report()
    labels = {c.label for c in report.checks}
    assert "OS" in labels
    assert "Display" in labels
    assert "Protocol observer" in labels
    assert "Transformice running" in labels


def test_format_report_renders_remedies() -> None:
    report = DoctorReport()
    report.add("Demo", "blocked", "nope", remedy="fix it")
    report.add("Demo2", "ok", "fine")
    text = format_report(report)
    assert "remedy:   fix it" in text
    assert "not ready" in text or "ready" in text


def test_ready_flag_false_without_game() -> None:
    report = DoctorReport()
    report.add("Transformice running", "missing", "no process")
    report.add("Protocol observer", "ok", "ok")
    assert report.ready_for_observation is False
