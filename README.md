# tfm-jev — Transformice × TypeSafe Jev

Experimental investigation: **can TypeSafe’s Jev control a real Transformice mouse (Steam/Proton) through typed, low-level keyboard decisions derived from structured state?**

This is **not** a traditional bot. There is no pathfinding, no `MOVE_TO`, no hardcoded `wall_jump()` routine. Deterministic code observes and describes physics; Jev chooses keys (or a short timed key sequence). Safety only validates and releases keys — it does not play the game for the model.

Conceptual pipeline and mode details: [`docs/architecture.md`](docs/architecture.md).

## What Jev controls

| Jev | Deterministic code |
|---|---|
| Next key state (raw mode) | Passive protocol observation |
| Short temporal key segments (chunked, later) | Raw → derived features (velocity, contacts, geometry) |
| | DecisionState schema + versioning |
| | Input scheduling, safety, `release_all` |
| | Recording, replay, analysis |

## Ubuntu requirements

- Ubuntu with Python **3.12+** and [uv](https://docs.astral.sh/uv/)
- Steam + Transformice (App ID 335240), launched via Proton
- X11 tools for injection: `xdotool` (game runs as XWayland window)
- Optional observe extra: raw socket capability for passive sniffing (see doctor)

## Install

```bash
uv sync                      # core + dev
uv sync --extra observe      # caseus + scapy (observation)
uv sync --extra jev          # typesafe-sdk (Jev modes)
uv sync --all-extras
```

Copy `.env.example` to `.env` and set `TYPESAFE_API_KEY` when you need Jev. Never commit keys.

## Doctor

```bash
uv run tfm-agent doctor
```

Detects OS, display server, Steam, Transformice install/running state, Proton, window geometry, input backends, and whether passive observation is possible. Prints exact remediation commands (e.g. `setcap` on the venv Python). No hardcoded username paths.

## Observe

With the game running:

```bash
uv run tfm-agent observe
uv run tfm-agent observe --json
```

Prints live state fields **only if they are really available** from the protocol source, with a final availability matrix (`AVAILABLE` / `UNAVAILABLE` + source). Missing fields are never faked.

## Record a human run

```bash
uv run tfm-agent record --label walljump-right
```

Writes `recordings/<date>_<label>.jsonl` (monotonic timestamps, raw state, derived state, input transitions, schema version).

## Analyze and replay

```bash
uv run tfm-agent analyze recordings/2026-…_walljump-right.jsonl
uv run tfm-agent replay recordings/2026-…_walljump-right.jsonl
```

`analyze` measures observation rate, jitter, transition intervals, contact periods — without assuming a correct wall-jump script. `replay` runs the state provider offline.

## Jev setup

```bash
export TYPESAFE_API_KEY=…    # official SDK variable (see .env.example)
uv run tfm-agent benchmark jev
uv run tfm-agent run --controller jev --control-mode raw --dry-run
```

Dry-run builds DecisionState, calls Jev, logs latency/probabilities, **sends no keys**.

## Control modes (after observation is proven)

```bash
uv run tfm-agent run --controller human
uv run tfm-agent run --controller jev --control-mode raw --dry-run
uv run tfm-agent run --controller jev --control-mode raw
# later, only if latency data justifies it:
uv run tfm-agent run --controller jev --control-mode chunked
```

Deadline policy: `--deadline-fallback keep|release`. Every fallback and deadline miss is logged. Bad results are results — we do not hide latency behind a helper controller.

## Safety

- `release_all()` on Ctrl+C, SIGTERM, exceptions, focus loss (default), stale state, emergency stop
- Focus gate: do not type into another window by default
- Default mode `unassisted`: no silent “smart” overrides of Jev’s keys

## Recording format

JSONL lines tagged with schema/prompt versions (`tfm-jev-state-v1`, `prompt-v1`). Contains observations, decisions, latencies, execution timestamps. Never API keys or game credentials.

## Experiment methodology

- Human baseline first, then Jev dry-run, then raw control, then benchmarks (wall climb, traversal, air-jump, …).
- Report attempts, success rate, latency, controller mode, prompt/schema version, map — never a single-run claim that “Jev learned wall-jump”.
- State rate ≠ decision rate; both are measured.

## Known limitations

- Self `x/y/vx/vy` may require read-only extraction of SWF `packet_key_sources` if the server does not echo self motion (see `docs/protocol-research.md`).
- `KeyboardPacket` is not guaranteed during normal arrow-key play; human key state is captured at OS level in recordings when protocol flags are absent.
- Passive capture needs `CAP_NET_RAW` once (`setcap` on venv Python).
- laya-mlx is Apple Silicon only and is **not** used here; Jev runs via the TypeSafe API.
- Substituting `Transformice.swf` with a proxy loader is out of default scope.

## License / ethics

Research tooling for controlled observation and typed control experiments. No memory injection, no credential theft, no binary patching, no anti-cheat bypass.
