"""Dump every clientbound packet kind + GenericWithID raw ids for one window."""

from __future__ import annotations

import argparse
import asyncio
import collections
import time

from tfm_agent.protocol.endpoints import discover_endpoints, endpoints_to_sniffer_targets, game_endpoints
from tfm_agent.protocol.observer import Observation, build_sniffer


async def run(duration: float) -> int:
    endpoints = discover_endpoints()
    if not game_endpoints(endpoints):
        print("no endpoints", flush=True)
        return 1

    counts: collections.Counter[str] = collections.Counter()
    generic_ids: collections.Counter[str] = collections.Counter()
    login_fields: list[dict] = []
    samples: list[Observation] = []

    def on_obs(obs: Observation, bound: str) -> None:
        key = f"{bound}:{obs.kind}"
        counts[key] += 1
        if obs.kind == "LoginSuccessPacket":
            login_fields.append(obs.fields)
            print(f"LOGIN_SUCCESS {obs.fields}", flush=True)
        if "GenericWithID" in obs.kind or obs.raw_id:
            rid = obs.raw_id or obs.fields.get("id")
            generic_ids[f"{bound}:{rid}"] += 1
        if bound == "clientbound" and len(samples) < 500:
            samples.append(obs)

    targets = endpoints_to_sniffer_targets(endpoints)
    sniffer = build_sniffer(targets, on_observation=on_obs)
    await sniffer.startup()
    task = asyncio.create_task(sniffer.listen())
    print(f"dumping {duration}s — RELOG/FULL RESTART the game NOW", flush=True)
    try:
        await asyncio.sleep(duration)
    finally:
        sniffer.close()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    print("\n=== clientbound counts ===")
    for k, v in sorted(counts.items()):
        if k.startswith("clientbound"):
            print(f"  {k}: {v}")
    print("\n=== generic raw ids ===")
    for k, v in sorted(generic_ids.items(), key=lambda x: -x[1])[:40]:
        print(f"  {k}: {v}")
    print(f"\nLoginSuccess fields captured: {len(login_fields)}")
    # Highlight if (26, 2) appears as generic
    for k, v in generic_ids.items():
        if "26" in k and "2" in k:
            print(f"NOTE: possible LoginSuccess as generic: {k} x{v}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--duration", type=float, default=45.0)
    args = p.parse_args(argv)
    return asyncio.run(run(args.duration))


if __name__ == "__main__":
    raise SystemExit(main())
