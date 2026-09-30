"""Live packet inspection (phase D gate) — dynamic endpoints, no hardcoded IPs."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect live Transformice packets")
    parser.add_argument("--duration", type=float, default=20.0, help="seconds to sniff")
    parser.add_argument(
        "--keys",
        default=None,
        help="comma-separated packet_key_sources (optional)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        from tfm_agent.protocol.endpoints import discover_endpoints, game_endpoints
        from tfm_agent.protocol.observer import run_observe
    except ImportError as exc:
        print(f"import failed: {exc}", file=sys.stderr)
        print("uv sync --extra observe", file=sys.stderr)
        return 1

    endpoints = discover_endpoints()
    games = game_endpoints(endpoints)
    if not games:
        print("no game endpoints — open Transformice and join a room", file=sys.stderr)
        print(f"all endpoints: {endpoints}", file=sys.stderr)
        return 1
    print(f"game endpoints: {games}", file=sys.stderr)

    keys: list[int] | None = None
    if args.keys:
        keys = [int(x.strip()) for x in args.keys.split(",") if x.strip()]

    import asyncio

    return asyncio.run(
        run_observe(
            duration_s=args.duration,
            packet_key_sources=keys,
            json_mode=args.json,
            endpoints=endpoints,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
