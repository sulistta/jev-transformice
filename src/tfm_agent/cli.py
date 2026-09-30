"""tfm-agent command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from tfm_agent import __version__
from tfm_agent.config import load_config


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tfm-agent",
        description="Transformice observation and TypeSafe Jev control experiments",
    )
    parser.add_argument("--version", action="version", version=f"tfm-agent {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="detect Steam/Proton/game/input/observer capabilities")

    observe = sub.add_parser("observe", help="print live raw state (no input injection)")
    observe.add_argument("--json", action="store_true", help="emit JSON lines")

    record = sub.add_parser("record", help="record human telemetry to JSONL")
    record.add_argument("--label", default="session", help="recording label")
    record.add_argument("--out", default="recordings", help="output directory")

    analyze = sub.add_parser("analyze", help="analyze a recording JSONL")
    analyze.add_argument("path")

    replay = sub.add_parser("replay", help="replay a recording through ReplayStateProvider")
    replay.add_argument("path")

    run = sub.add_parser("run", help="run a controller (human | jev)")
    run.add_argument("--controller", choices=("human", "jev"), default="human")
    run.add_argument("--control-mode", choices=("raw", "chunked"), default="raw")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument(
        "--deadline-fallback",
        choices=("keep", "release"),
        default=None,
        help="override decision.fallback",
    )

    experiment = sub.add_parser("experiment", help="named experiments")
    experiment.add_argument(
        "name",
        choices=(
            "inspect-packets",
            "inspect-caseus",
            "proxy-smoke-test",
            "self-echo",
        ),
    )
    experiment.add_argument("--duration", type=float, default=None)
    experiment.add_argument("--skip-correlation", action="store_true")
    experiment.add_argument("--non-interactive", action="store_true")
    experiment.add_argument("--json", action="store_true")

    benchmark = sub.add_parser("benchmark", help="latency / rate benchmarks")
    benchmark.add_argument("target", choices=("jev", "observer", "input"))

    return parser


def cmd_doctor() -> int:
    from tfm_agent.doctor import collect_report, format_report

    report = collect_report()
    print(format_report(report))
    return 0 if report.ready_for_observation else 1


def cmd_observe(args: argparse.Namespace) -> int:
    import asyncio

    from tfm_agent.protocol.endpoints import discover_endpoints, game_endpoints
    from tfm_agent.protocol.observer import run_observe

    endpoints = discover_endpoints()
    if not game_endpoints(endpoints):
        print(
            "observe: no game endpoints — launch Transformice and join a room.\n"
            "Run: uv run tfm-agent doctor",
            file=sys.stderr,
        )
        if args.json:
            print(json.dumps({"status": "no_endpoints"}))
        return 1

    return asyncio.run(run_observe(duration_s=None, json_mode=args.json))


def cmd_record(args: argparse.Namespace) -> int:
    print(
        f"record --label {args.label}: not implemented until observation gate passes (phase E).",
        file=sys.stderr,
    )
    return 2


def cmd_analyze(args: argparse.Namespace) -> int:
    print(f"analyze {args.path}: not implemented until first recording (phase E).", file=sys.stderr)
    return 2


def cmd_replay(args: argparse.Namespace) -> int:
    print(f"replay {args.path}: not implemented until first recording (phase E).", file=sys.stderr)
    return 2


def cmd_run(args: argparse.Namespace) -> int:
    config = load_config()
    controller = args.controller
    mode = args.control_mode
    fallback = args.deadline_fallback or config.decision.fallback
    print(
        "run: not implemented until observation + input backend gates (phases F1–F2).\n"
        f"planned: controller={controller} mode={mode} dry_run={args.dry_run} "
        f"fallback={fallback} max_state_age_ms={config.decision.max_state_age_ms}",
        file=sys.stderr,
    )
    return 2


def cmd_experiment(args: argparse.Namespace) -> int:
    if args.name == "inspect-caseus":
        return _run_script("inspect_caseus")
    if args.name == "inspect-packets":
        return _run_script("inspect_packets", argv=["--duration", "20"])
    if args.name == "self-echo":
        argv: list[str] = []
        if args.duration is not None:
            argv.extend(["--duration", str(args.duration)])
        if args.skip_correlation:
            argv.append("--skip-correlation")
        if args.non_interactive:
            argv.append("--non-interactive")
        if args.json:
            argv.append("--json")
        return _run_script("self_echo", argv=argv)
    print(
        f"experiment {args.name}: not implemented.",
        file=sys.stderr,
    )
    return 2


def _run_script(stem: str, argv: list[str] | None = None) -> int:
    import importlib.util

    from tfm_agent.config import PROJECT_ROOT

    path = PROJECT_ROOT / "experiments" / f"{stem}.py"
    if not path.is_file():
        print(f"missing {path}", file=sys.stderr)
        return 1
    spec = importlib.util.spec_from_file_location(stem, path)
    if spec is None or spec.loader is None:
        print(f"cannot load {stem}", file=sys.stderr)
        return 1
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    main_fn = getattr(module, "main", None)
    if main_fn is None:
        print(f"{stem} has no main()", file=sys.stderr)
        return 1
    result = main_fn(argv) if argv is not None else main_fn()
    return int(result or 0)


def cmd_benchmark(args: argparse.Namespace) -> int:
    print(
        f"benchmark {args.target}: not implemented until the corresponding subsystem exists.",
        file=sys.stderr,
    )
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    handlers = {
        "doctor": lambda: cmd_doctor(),
        "observe": lambda: cmd_observe(args),
        "record": lambda: cmd_record(args),
        "analyze": lambda: cmd_analyze(args),
        "replay": lambda: cmd_replay(args),
        "run": lambda: cmd_run(args),
        "experiment": lambda: cmd_experiment(args),
        "benchmark": lambda: cmd_benchmark(args),
    }
    return handlers[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())
