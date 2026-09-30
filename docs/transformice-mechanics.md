# Transformice mechanics

Labels used everywhere:

- **documented** — stated by wiki, official guides, or client-facing docs (may be outdated).
- **observed** — seen in our own telemetry (date + recording id).
- **hypothesis** — plausible reading of documented behavior; not yet tested here.
- **verified experimentally** — measured in this project with a recording.
- **unknown** — no reliable source; do not encode in features.

Numeric values from wiki/old posts are **hypotheses** until `verified experimentally` on the current Steam client. We never hardcode them as ground truth in feature extraction.

## Coordinate system (hypothesis → verify in Phase D)

- Origin top-left; x increases right; y increases **down** (standard for Atelier801/Transformice maps and Lua docs).
- Map XML defines grounds in this space; player position in packets uses scaled integers (`100/30` scale in caseus types) — **exact unit mapping unknown until compared to XML**.

## Horizontal movement

| Item | Status |
|---|---|
| Left/right keys or A/D move the mouse | **documented** (wiki Controls) |
| Acceleration / max speed / friction values | **unknown** (wiki-era numbers are **hypothesis**) |
| Ground friction depends on surface type/friction attribute | **documented** (map editor: friction float; Lua `bodyDef.friction`) |
| Caseus `PlayerFrictionInfo.charge` sticky (>0) / slippery (<0) | **documented in code**; semantics for wall-jump **hypothesis** until observed |

## Gravity and air control

| Item | Status |
|---|---|
| Gravity pulls +y (down) | **documented** |
| Player retains horizontal input while airborne | **documented** (gameplay); magnitude **unknown** |
| Gravity value / terminal velocity | **unknown** numerically |

## Jump and air-jump

| Item | Status |
|---|---|
| Jump = Up/W | **documented** |
| Landing sets an internal "standing" state that still allows a jump after walking off a ledge (air-jump / "double jump") | **documented** (Steam guide 2015: walking off a platform does not set state to falling) |
| Using the jump clears the pending jump until next valid landing | **documented** (same guide) |
| Air-jump resets vertical velocity (breaks fall) | **documented** (guide: "airjumping will reset your velocity to zero… jump normally"); exact reset behavior **hypothesis** |
| `grounded` (contact with floor) vs `jump_available` (internal standing credit) are **not** equivalent | **documented** (guide) → must appear as separate derived fields |
| Explicit `jump_available` flag in protocol | **unknown**; inference from contact history + last jump + vy = **hypothesis** marked `derived` |
| Holding jump while moving auto-jumps on landing; turning while holding can cancel | **documented** (wiki wall-jump problems) |

## Wall-jump (escalade)

| Item | Status |
|---|---|
| Requires contact with a wall **while falling** (vy > 0 in screen coords), then a jump that reacquires the wall | **documented** (wiki + Steam guide: falling + new contact → game treats wall like ground) |
| Sequence human description: toward wall, on contact jump away, recontact while falling, repeat; **do not hold jump** at impact | **documented** (wiki Controls/Wall jump) |
| Ground friction must be ≥ 3 for normal wall-jump (wiki); friction 0 (default ice/lava/trampoline) fails | **documented** → **hypothesis** for current client |
| Trampoline wall-jump variant: press **toward** the surface, not away | **documented** |
| Chocolate/high-friction: hold direction into wall + mash jump (slow climb) | **documented** |
| Cheese increases mass → longer air time, harder to return to wall | **documented** |
| This is treated as an exploit/bug of "touching while falling ≈ grounded" | **documented** (wiki How it works) |
| Exact input timing in ms for a successful cycle | **unknown** → human `record` + `analyze` (Phase E) |
| Our architecture must **not** implement `wall_jump()` as code | **project rule** (spec §5) — wall-jump emerges from Jev key choices |

## Corner-jump

| Item | Status |
|---|---|
| Mouse hitbox treated as circle; corner×corner contact behaves like a diagonal ramp converting vy→vx | **documented** (wiki Corner jump) |
| Long jump: stand at edge until almost stopped, then run+jump; worse with cheese | **documented** |
| Timing window and angle sensitivity | **unknown** → needs human corner-jump recordings before any benchmark |

## Turn-around / long-jump

| Item | Status |
|---|---|
| Turn-around listed as a bootcamp technique | **documented**; precise input pattern **unknown** here |
| Long jump ≈ edge positioning + jump (see corner-jump) | **documented** |

## Surfaces and objects

| Surface | Status |
|---|---|
| Wood/default: normal wall-jump | **documented** |
| Chocolate: high friction, wall-jump possible; mash-jump climb | **documented** |
| Ice: friction 0 default → no normal wall-jump; steep ice climb variant | **documented** |
| Lava: kills on contact (timing jump onto horizontal lava face); no normal wall-jump | **documented** |
| Trampoline: bounce; wall-jump variant toward surface | **documented** |
| Water: swim/sink behavior; "water cornering" exists | **documented** (existence); details **unknown** |
| Honey/web (spider web): caseus has `AddSpidermouseWebPacket (5,36)` | **documented in code**; effect **unknown** |
| Wind: map property / Lua | **documented** (existence); model **unknown** |
| Moving/dynamic grounds: Lua `moveObject`, `dynamic` bodies in map XML | **documented** |
| Conjuration, shaman objects, portals | **documented** (packets exist: Portal enum on movement) |

## Cheese effects

| Item | Status |
|---|---|
| Carrying cheese increases mass → affects jumps and wall-jumps | **documented** |
| Cheese position relative to player available from map XML + cheese events | **hypothesis** until Phase D |
| `has_cheese` for self: from `GetCheesePacket` / hole / PlayerInfo.cheeses / death reset | **partially documented in code**; exact self flag **to verify** |

## Map XML

| Item | Status |
|---|---|
| New round delivers XML string (possibly empty for vanilla) | **documented in code** (`NewRoundPacket.xml`) |
| Grounds: position, size, rotation, friction, restitution, type, dynamic flag, mice/ground collision | **documented** (map editor / Lua `addPhysicObject` / wiki) |
| Cheese, holes, spawn points present in XML for vanilla/editor maps | **documented** |
| Parsing strategy: physical properties only, no cosmetics | **project rule** |

## Physics authority

| Item | Status |
|---|---|
| Client reports its own motion to server (`PlayerMovementPacket` serverbound) | **documented in code** |
| Server echoes/relays movement to other clients with `session_id` | **documented in code** |
| Whether self also receives a clientbound echo of its own motion | **unknown** → experiment |
| Server may correct position (MovePlayerPacket) | **documented in code** |

## Decision-relevant derived fields (allowed)

Physical, neutral features only:

- `estimated_vx/vy` (protocol or finite difference, with `source`)
- `ascending` / `falling` from vy sign (axis-aware)
- `grounded` (recent floor contact hypothesis) and `jump_available` (separate credit hypothesis) — both `derived` until protocol flag found
- `left_contact` / `right_contact` / `below` from proximity to grounds (geometry engine)
- distances to nearest wall/floor/ceiling/corners, surface friction of contact ground
- relative `cheese_dx/dy`, `hole_dx/dy`

## Forbidden as features (until strong experimental justification)

- `wall_jump_possible`, `best_direction`, `route`, `safe_action`, `corner_jump_now`
