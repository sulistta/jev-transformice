"""Verify caseus import and basic packet machinery without network access."""

from __future__ import annotations

import sys


def main() -> int:
    try:
        import caseus
    except ImportError as exc:
        print(f"caseus import failed: {exc}", file=sys.stderr)
        print("Install with: uv sync --extra observe", file=sys.stderr)
        return 1

    print(f"caseus: OK ({getattr(caseus, '__file__', 'unknown')})")
    try:
        from caseus.packets import Packet, clientbound, serverbound  # noqa: F401
    except ImportError as exc:
        print(f"caseus.packets import failed: {exc}", file=sys.stderr)
        return 1
    print("caseus.packets: OK")

    try:
        from caseus.packets.serverbound import PlayerMovementPacket
        from caseus.packets.clientbound import NewRoundPacket

        print(f"PlayerMovementPacket id={PlayerMovementPacket.id}")
        print(f"NewRoundPacket id={NewRoundPacket.id}")
    except Exception as exc:  # pragma: no cover - depends on caseus version
        print(f"packet class lookup failed: {exc}", file=sys.stderr)
        return 1

    print("inspect_caseus: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
