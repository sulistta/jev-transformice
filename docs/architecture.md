# Architecture

## Goal

Measure whether **TypeSafe Jev** can control a Transformice mouse through **low-level typed keyboard decisions** derived from structured state — not whether we can write a traditional platformer bot.

Code owns: observation, parsing, deterministic feature/geometry extraction, timing, safety, recording.  
Jev owns: which keys are pressed and when (raw mode) or a short temporal key plan (chunked mode).

## Pipeline

```text
Steam + Proton → Transformice
       ↓
protocol observer (passive sniff / events)
       ↓
RawGameState          (timestamps monotonic, raw fields only)
       ↓
feature extraction     (velocity, contacts, local geometry, relative objective)
       ↓
DecisionState          (versioned, compact, tfm-jev-state-v1)
       ↓
┌──────┴──────┐
│  JEV RAW    │  next InputState
│ JEV CHUNKED │  list of timed segments  (later phase)
└──────┬──────┘
       ↓
validation + safety    (malformed, stale, focus, emergency — no “smart” play)
       ↓
TemporalInputExecutor  (monotonic schedule, cancel, replace future)
       ↓
InputBackend           (x11 | wayland | mock)  →  release_all guaranteed
       ↓
Transformice
```

Parallel path (no AI):

```text
human play → Recorder → JSONL → Analyzer → timing tables → design decisions
```

## Clocks

Three independent clocks; never collapse them:

1. **Observation clock** — packet/event arrival; measure Hz, jitter, state age.
2. **Decision clock** — Jev request completion; may be 4 Hz while observation is 50 Hz.
3. **Execution clock** — monotonic schedule for key transitions.

Rules:

- **Latest state wins.** A pending decision request holds at most one state; newer states replace the pending one (coalesce; count replacements).
- Do not assume `one observation = one API call`.
- Every decision records: `state_timestamp`, `request_start`, `request_end`, `latency`, `state_age_at_execution`, `deadline_missed`.
- Stale results: if age at completion > `max_state_age_ms`, discard and log `decision_discarded_stale` (do not silently apply).

## Raw vs derived

```python
RawGameState.timestamp_monotonic: float
RawGameState.self_player.position / velocity / ...
# every derived field carries source: "protocol" | "finite_difference" | "geometry" | "inferred"
```

Never silently mix observation and inference. Absent protocol fields stay `None`, not zeros.

## DecisionState (`tfm-jev-state-v1`)

Compact, relative features:

- motion: x, y, vx, vy, ascending/falling, jump_available (derived), has_cheese
- current input: left/right/jump/down
- contacts: left/right/below + contact ground friction when known
- nearby geometry: wall/floor distances and dy spans (physics primitives only)
- objective: cheese/hole relative dx/dy when known
- optional short history: few (dt, x, y) samples — add only if vx/vy+contacts prove insufficient

Schema id and prompt id are stored on every recording (`tfm-jev-state-v1`, `prompt-v1`).

## Input model

Action space = real key states, not verbs:

```text
NONE, LEFT, RIGHT, JUMP, LEFT_JUMP, RIGHT_JUMP, DOWN, …
```

Chunked mode (later): segments `{duration_ms, left, right, jump, down}` with limits:

```text
max_segments, min_segment_ms, max_segment_ms, max_horizon_ms
```

Defaults are experimental (`4 / 20 / 200 / 350`) until human telemetry retunes them.

Transitions are logged with monotonic timestamps: requested, executed.

## Executor and safety

`TemporalInputExecutor` only: press, release, wait until monotonic time, cancel, replace unexecuted tail.  
It does not know physics, maps, cheese, or AI.

Safety may block: malformed decision, unknown key, impossible duration, stale decision/state, provider disconnect, window gone, process exit, emergency stop, focus loss (configurable).  
Safety may **not** choose directions. Direction-changing shields require an explicit `assisted` mode; default is `unassisted`. If ever added, logs must show `jev_proposed`, `executed`, `shield_intervened`, `shield_reason`.

## Fallbacks

Explicit only:

- `--deadline-fallback keep` — hold current input state
- `--deadline-fallback release` — release all keys

No `FALLBACK_SMART_CONTROLLER`. Every fallback is logged.

## Providers

```text
LiveStateProvider   — sniff + parse current game
ReplayStateProvider — feed recorded JSONL
```

Both implement the same Protocol so controllers and tests never care which is active.

## Recording format

JSONL, one event per line, schema-versioned. Each run records:

- run id, wall date, code commit if available
- controller, control mode, model, prompt/schema version
- map code, raw observations, derived features
- Jev requests/responses/probabilities/latency
- input commands + execution timestamps, deadline misses
- death / success / round end when observable

Never record API keys or game credentials.

## Modes

| Command | Role |
|---|---|
| `doctor` | environment + capability report |
| `observe` | live state printing (no input injection) |
| `record` | human telemetry capture |
| `analyze` | offline statistics from JSONL |
| `replay` | Replayer over recording, no game |
| `run --controller human` | observe+log only |
| `run --controller jev --dry-run` | full loop without keyboard |
| `run --controller jev --control-mode raw` | Jev → next keys |
| `run --controller jev --control-mode chunked` | Jev → short segment plan (later) |
| `benchmark jev` / `benchmark observer` / `benchmark input` | latency / rate studies |

## Explicit non-goals (initial)

Pathfinding, navigation graphs, `MOVE_TO`, hardcoded wall-jump/corner-jump routines, vision-first observation, premature optimization (web UI, DB, Docker, RL).
