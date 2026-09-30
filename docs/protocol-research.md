# Protocol research — Transformice observation without a headless client

Research date: 2026-09-22. Sources: repository source code (read, not assumed), live process inspection on Ubuntu, official docs. Every claim is labeled.

## Central question

> Can we observe the real Steam/Proton Transformice client through a proxy or passive capture, without turning the agent into a separate headless client?

**Answer (supported):** yes for passive observation of the TCP game connection, with caveats on ciphered packets. A full caseus MITM proxy requires the `tfm-proxy-loader` (replacing `Transformice.swf`), which modifies game files and is out of the default scope. Headless clients (aiotfm, Transfromage) do **not** observe the Steam client; they are separate sessions.

## Ecosystem status

| Project | Language | Last known state | Python compat | Linux | Role for us |
|---|---|---|---|---|---|
| [friedkeenan/caseus](https://github.com/friedkeenan/caseus) | Python | Active (156 commits), no docs/tests of note, **not on PyPI** | requires-python `>=3.7`; deps `pak` (>=3.10), scapy | Yes | **Primary**: packet definitions, `Sniffer`, `Proxy`, `Client` |
| [Athesdrake/aiotfm](https://github.com/Athesdrake/aiotfm) | Python | PyPI 1.4.9 (2024-09-22) | Async client | Yes | Headless only; API shape reference. Needs external key endpoint + token |
| [tocuto/transfromage](https://github.com/tocuto/transfromage) | Python | **Discontinued**; needs protocol patch | Legacy threads | Yes | Historical only |
| [Lautenschlager-id/transfromage](https://github.com/Lautenschlager-id/transfromage) | Lua (Luvit) | Maintained-ish | n/a | Yes | Headless only |
| [Athesdrake/detfm](https://github.com/Athesdrake/detfm) | Python/RE | Deobfuscation tool | n/a | Yes | SWF analysis reference |
| [friedkeenan/tfm-proxy-loader](https://github.com/friedkeenan/tfm-proxy-loader) | AS3/SWF | Active | n/a | Via Proton | Forces client to `localhost:11801`. **Replaces `Transformice.swf`** → out of default scope; opt-in only with explicit consent |
| [friedkeenan/tfm-secrets-leaker](https://github.com/friedkeenan/tfm-secrets-leaker) | Python/AS3 | Active | n/a | Yes | Read-only extraction of hardcoded SWF secrets (server address/ports, game version, auth key, packet key sources, verification template) |
| [Tocutoeltuco/tfmplugins](https://github.com/Tocutoeltuco/tfmplugins) | Python | 2020, Windows driver | 3.x | Windows-oriented | Passive sniff proof-of-concept; confirms message keys obtainable, identification keys not |
| [extremq/tfm-tools](https://github.com/extremq/tfm-tools) | Python | 2021 | 3.x | Yes | packet_viewer via plugins |

### caseus capabilities (read from source)

- `caseus/packets/{serverbound,clientbound}` — large set of typed packets (`pak` library).
- `caseus/proxies/proxy.py` — full MITM: main port 11801, satellite 12801, socket policy 10801; corrects loader size `0x1FBD`; listens for `MainServerInfoPacket` / `KeySourcesPacket` / `AuthKeyPacket`.
- `caseus/proxies/input.py` — `InputListeningProxy` observes `serverbound.KeyboardPacket` and `serverbound.MouseDownPacket` via Lua `bindKeyboard`/`bindMouseDown` (map-dependent, **not** always present).
- `caseus/sniffers/sniffer.py` — **passive** `scapy.AsyncSniffer` reassembly of TCP streams; no proxy, no client modification. Hardcodes `MAIN_IP_ADDR = "51.38.60.113"` and ports `[11801, 12801, 13801, 14801]` — **must be replaced by dynamic detection** for the live client (we observed `transformice.com` → OVH `54.37.233.52`, including port 80 in one session).
- `caseus/clients/client.py` — headless client (handshake/login/verification). **Not** what we use for observation.
- `caseus/__main__.py` — `caseus proxy`, `caseus server`, `caseus shakikoo`.

Dependency chain: `pak` (PyPI 1.1.2, requires-python `>=3.10`), `atpublic`, `fixedint`, `aioconsole`, `aiohttp`, `scapy`.

## Live environment facts (observed 2026-09-22)

```
Steam root candidates: ~/.local/share/Steam and ~/.steam/steam (symlink)
App ID: 335240  (appmanifest_335240.acf name "Transformice")
Install: steamapps/common/Transformice/{Transformice.exe, Transformice.swf, steam_api.dll, Adobe AIR/, META-INF/}
Compat data: steamapps/compatdata/335240/pfx
Proton in use: "Proton 8.0" (process cmdline); also installed: Proton 9.0 (Beta), Proton - Experimental, GE-Proton*, UMU-Proton*
Session: Wayland (XDG_SESSION_TYPE=wayland) + XWayland (DISPLAY=:0)
Game windows: xdotool search --name Transformice → 2 X11 windows (e.g. 828x666)
Process: Transformice.exe under wine, pid discoverable via /proc
TCP: Transformice.exe had ESTAB to 54.37.233.52:80 (transformice.com / OVH) and localhost sockets
Raw capture: tcpdump present but no cap_net_raw → Operation not permitted (until setcap)
/dev/uinput: root:root 0660; user not in `input` group; ydotool installed, no daemon running
```

## Cipher model (from caseus source)

| Cipher | Name | Used by (examples) |
|---|---|---|
| `IDENTIFICATION` (XXTEA) | login | `serverbound.LoginPacket (26,8)` |
| `XOR` ("msg") | message | `RoomMessagePacket (6,6)`, `CommandPacket (6,26)`, **`KeyboardPacket (29,2)`**, **`PlayerMovementPacket (149,26)`** |
| `INVOCATION` (XXTEA) | shaman objects | `AddShamanObjectPacket (5,20)` |
| none | plaintext | Most clientbound packets (map, timer, events); many serverbound gameplay reports |

`packet_key_sources` (rotating secrets embedded in the served SWF) are required to (de)cipher XOR/XXTEA bodies. A passive sniffer **without** key sources can still parse packets whose `CIPHER is None`; ciphered packets must be treated as `GenericWithID` (opaque) unless secrets are supplied.

`tfm-secrets-leaker` documents that the main SWF (and most secrets) changes about every five minutes for the web client; **Steam/AIR rotation behavior is a hypothesis until measured**.

## Movement and self-state packets (read from caseus)

### Serverbound — self report (client → server)

```text
PlayerMovementPacket  id=(149, 26)  CIPHER=XOR
  round_id: LEB128
  moving_right: bool
  moving_left:  bool
  x: ScaledInteger(LEB128, 100/30)
  y: ScaledInteger(LEB128, 100/30)
  velocity_x: ScaledInteger(LEB128, 10)
  velocity_y: ScaledInteger(LEB128, 10)
  friction_info: PlayerFrictionInfo   # charge>0 sticky, charge<0 slippery
  jumping: bool
  jumping_frame_index: LEB128
  entered_portal: Portal enum
  rotation_info: optional             # transformed/rolling only
```

```text
KeyboardPacket  id=(29, 2)  CIPHER=XOR
  key_code, down, x, y, velocity_x, velocity_y
  → only when the map/server binds keys (Lua bindKeyboard); NOT guaranteed for arrow-key movement
```

```text
GetCheesePacket   id=(5, 19)  plaintext — round_id, x, y, cheese_index, distance
EnterHolePacket   id=(5, 18)  plaintext — hole_type, round_id, map_code, x, y
PlayerDiedPacket  id=(4, 5)   plaintext — round_id, death type
SetFacingPacket   id=(4, 6)   plaintext — facing_right
```

### Clientbound — world state (server → client), typically plaintext

```text
NewRoundPacket        id=(5, 2)  — map_code, round_id, xml (CompressedString), author, category, …
SetRoundTimerPacket   id=(5, 22) — seconds
PlayerMovementPacket  id=(144, 48) — session_id + same motion fields as (149,26)  [other mice]
MovePlayerPacket      id=(8, 3)  — x, y, velocity_x/y (Lua movePlayer / shaman)
LoginSuccessPacket    — session_id  (self identity)
JoinedRoomPacket      id=(5, 21) — room name
SetShamanPacket / PlayerInfo — roster with session_id, username, cheeses, score
```

**Implication:** map XML, round timer, cheese/hole/death events, and *other players'* motion are available without secrets. **Self** `x/y/vx/vy` live in the XOR-ciphered serverbound `(149,26)` (and possibly clientbound echoes keyed by our `session_id` — must be verified empirically). If clientbound does not echo self motion, we need `packet_key_sources` via **read-only SWF extraction** (user-approved) to decipher `(149,26)`.

### Availability matrix (pre-experiment)

| Field | Expected source | Availability |
|---|---|---|
| map XML | clientbound `(5,2)` | AVAILABLE (no secrets) |
| round time | clientbound `(5,22)` | AVAILABLE (no secrets) |
| other players | clientbound `(144,48)` + PlayerInfo | AVAILABLE (no secrets) |
| cheese/hole/death events | serverbound plaintext | AVAILABLE (no secrets) |
| self x/y/vx/vy | serverbound `(149,26)` XOR | AVAILABLE **iff** key sources extracted; else UNAVAILABLE |
| keyboard flags (human) | `KeyboardPacket` only if bound; else not on wire | Likely UNAVAILABLE for normal play → record input via OS-level logging in `record` |
| self session_id | clientbound LoginSuccess | AVAILABLE after login |
| cheese held / dead flags | inferred from events or PlayerInfo cheeses | To verify |

This table is updated by `tfm-agent observe` (source column), not by assumption.

## Input path (OS, not protocol)

The agent does **not** inject protocol packets for control (that would be a different experiment). Control = Linux input events to the focused game window:

- Session is Wayland but the game is an **X11/XWayland** window → `xdotool` (XTEST) works for search/focus/geometry and can send keys when focused.
- `ydotool` + `/dev/uinput` is the Wayland-native fallback; currently blocked by device permissions (`root:root 0660`, user not in `input`).
- Backend interface stays `set_state` / `release_all` so either can be swapped; selection is automatic in `doctor`.

## What we deliberately do not do

- DLL injection, process memory reads, credential/token extraction, password interception, executable/SWF patching, anti-cheat bypass, stealth.
- Replacing `Transformice.swf` with `tfm-proxy-loader` (documented as opt-in future only; requires explicit user consent + restore procedure).
- Treating headless clients as if they observed the Steam session.

## Open questions (resolved only by experiment)

1. Does clientbound echo self motion (session_id-matched `(144,48)` or other packet), or only serverbound `(149,26)`?
2. Do SWF-extracted `packet_key_sources` match the live Steam session, and how often do they rotate under Proton?
3. Actual packet/state rate (Hz) and jitter on this connection.
4. Whether `KeyboardPacket` ever appears during normal arrow-key play (expected: no, unless map binds keys).
5. Exact TCP 5-tuple stability across rounds/satellite server switches (caseus sniffer must follow `ChangeSatelliteServerPacket`).

## Commands for the next step

```bash
uv run tfm-agent doctor
uv run tfm-agent experiment inspect-packets
uv run tfm-agent observe
uv run tfm-agent observe --json
```

---

# Phase D gate — live results (2026-09-22)

Passive observation via patched caseus `Sniffer` with **dynamic endpoints** from `/proc` (no hardcoded IPs). `setcap` applied to venv Python; doctor status: **ready for observation**.

## Availability matrix (keys = none)

| Field | Status | Source |
|---|---|---|
| `map_code` | **AVAILABLE** | clientbound `NewRoundPacket` (5,2) |
| `round_time` | **AVAILABLE** | clientbound `SetRoundTimerPacket` (5,22) |
| `others_x_y` / `other_players` | **AVAILABLE** | clientbound `PlayerMovementPacket` (144,48) — x, y, vx, vy, session_id |
| `session_id` | CONDITIONAL | clientbound `LoginSuccessPacket` (26,2) — only if observe window includes login/room switch |
| `self_x_y` / `self_vx_vy` | **UNAVAILABLE without keys** | serverbound (149,26) is XOR → `GenericWithID` until `packet_key_sources`; clientbound self-echo possible once `session_id` known |
| `cheese_xy` | event-gated | serverbound `GetCheesePacket` (5,19) plaintext — play during observe |
| `hole_xy` | event-gated | serverbound `EnterHolePacket` (5,18) plaintext |
| `death` | event-gated | serverbound `PlayerDiedPacket` (4,5) plaintext |
| `keyboard` | UNAVAILABLE | `KeyboardPacket` (29,2) XOR + only if `bindKeyboard` |

## Live endpoints (rotating)

- Main: `51.195.117.72:11801`
- Satellite/world: e.g. `37.187.79.102:12801`, `149.202.72.87:13801`
- HTTP side channels on port 80 (ignored by sniffer filter)

Discovery: `tfm_agent.protocol.endpoints.discover_endpoints()` → socket inode ∩ `/proc/net/tcp` for Transformice.exe + wineserver.

## caseus fixes applied in-project

1. Import path: `from caseus.sniffers import Sniffer` (not `caseus.Sniffer`).
2. Serverbound decipher bug patched: `decipher_data(buf, ctx=..., fingerprint=...)`.
3. Dynamic `sniffer.main.ip_addr` / `.ports` + satellite slot from discovery.
4. `_packet_fields` serializes ScaledInteger/fixedint → float for JSON.

## Packet key sources (static extract blocked)

- Format: exactly **8** unsigned bytes.
- Steam `Transformice.swf` is a **loader only** (ZWS); live SWF fetched from transformice.com and assembled from DefineBinaryData blobs.
- Key bytes are **runtime-mixed** (no static literal in ~1266 decompiled scripts); rotate on the order of minutes (tfm-secrets-leaker README).

## Implication for DecisionState

- **Others** + **map geometry/timer** are solid for phase E recording.
- **Self continuous pose** remains the gate field: needs keys **or** LoginSuccess + clientbound self-echo.
- Event-based self samples (`GetCheese`/`EnterHole`/`PlayerDied`) are plaintext sparse ground-truth.
