from __future__ import annotations

from tfm_agent.protocol.endpoints import (
    Endpoint,
    classify,
    endpoints_to_sniffer_targets,
    game_endpoints,
)


def test_game_endpoints_filters_ports() -> None:
    eps = [
        Endpoint("51.195.117.72", 11801, "tcp"),
        Endpoint("51.77.132.45", 13801, "tcp"),
        Endpoint("51.75.128.119", 80, "tcp"),
        Endpoint("127.0.0.1", 631, "tcp"),
    ]
    games = game_endpoints(eps)
    assert [(e.ip, e.port) for e in games] == [
        ("51.195.117.72", 11801),
        ("51.77.132.45", 13801),
    ]


def test_classify() -> None:
    eps = [
        Endpoint("1.2.3.4", 11801, "tcp"),
        Endpoint("5.6.7.8", 80, "tcp"),
        Endpoint("9.9.9.9", 53, "udp"),
        Endpoint("8.8.8.8", 9999, "tcp"),
    ]
    c = classify(eps)
    assert len(c["game"]) == 1
    assert len(c["http"]) == 1
    assert len(c["udp"]) == 1
    assert len(c["other"]) == 1


def test_sniffer_targets_main_and_satellite() -> None:
    eps = [
        Endpoint("10.0.0.1", 12801, "tcp"),
        Endpoint("10.0.0.2", 11801, "tcp"),
        Endpoint("10.0.0.2", 11802, "tcp"),
    ]
    t = endpoints_to_sniffer_targets(eps)
    assert t["main"]["ip"] == "10.0.0.2"  # lowest port = main
    assert t["main"]["ports"] == [11801, 11802]
    assert t["satellite"]["ip"] == "10.0.0.1"
    assert t["satellite"]["ports"] == [12801]


def test_sniffer_targets_empty() -> None:
    t = endpoints_to_sniffer_targets([])
    assert t["main"] is None
