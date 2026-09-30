# Steam + Proton setup (Ubuntu)

This project assumes:

```text
Ubuntu Linux
Steam for Linux
Transformice installed via Steam
Transformice launched through Proton
Python agent runs natively on Ubuntu (outside Wine/Proton)
```

No absolute path contains a username in code. Discovery order:

1. Environment overrides (`TFM_AGENT_STEAM_ROOT`, etc.)
2. `$STEAM_DIR`, `$HOME/.steam/steam`, `$HOME/.local/share/Steam`, `$HOME/.steam/root`
3. First existing candidate that contains `steamapps`

## Observed reference environment (2026-09-22)

Documented as a **reference snapshot**, not a requirement:

```text
Display session: Wayland + XWayland (DISPLAY=:0)
Steam root: ~/.local/share/Steam (with ~/.steam/steam link)
Transformice App ID: 335240
Install dir: steamapps/common/Transformice
  Transformice.exe, Transformice.swf, steam_api.dll, Adobe AIR/, META-INF/
Compat data: steamapps/compatdata/335240/pfx
Proton in use at the time: Proton 8.0
Other tools present: xdotool (works on game X11 window), ydotool (uinput blocked),
  tcpdump/scapy (raw socket blocked until setcap), uv, Python 3.12
Game windows: two X11 windows titled "Transformice" visible to xdotool
```

`uv run tfm-agent doctor` re-detects all of this; do not copy paths from this file into scripts.

## Launch

Launch Transformice from Steam as usual (Proton). The agent never launches or patches the game in the default workflow.

## Process discovery

`doctor` walks `/proc/*/cmdline` looking for:

- `Transformice.exe` (game process)
- `.../Proton .../proton` and wineserver (Proton tree)
- steam reaper / pressure-vessel wrappers (optional context)

It extracts Proton version from the path segment (`Proton 8.0`, `GE-Proton11-5`, …).

## Network observation permission (one-time)

Passive sniffing needs `CAP_NET_RAW` (or `CAP_NET_ADMIN` for some filters). Until granted, `tcpdump`/`scapy` fail with `Operation not permitted`.

After `uv sync`, grant capability on the **project venv** Python only (not system Python):

```bash
sudo setcap cap_net_raw,cap_net_admin+eip "$(readlink -f .venv/bin/python)"
```

`doctor` prints the exact command with the resolved interpreter path when the capability probe fails. Re-run `uv sync` / recreate venv → repeat `setcap`.

The agent itself never runs as root.

## Input injection

| Backend | When | Requirements |
|---|---|---|
| `x11` (xdotool/XTEST) | default when game window is X11/XWayland | `xdotool` installed; ability to focus the game window |
| `wayland` (ydotool/uinput) | if X11 injection fails or session forbids XTEST | `/dev/uinput` writable by user (typically `sudo usermod -aG input $USER` + relogin) and `ydotool` daemon as needed |
| `mock` | tests, dry runs | none |

Focus policy (default on): do not send keys unless the Transformice window is focused; on focus loss → `release_all()` and pause execution.

## Emergency stop

- `Ctrl+C` / SIGINT / SIGTERM → `release_all()` then exit
- CLI-provided pause/stop path always releases keys
- Optional global hotkey can be added later; not required for Phase C

## Firewall / ports

Game uses custom TCP (historically ports 11801, 12801, 13801, 14801; live observation may differ, including port 80 to OVH). The observer follows the process’s actual sockets via `/proc/<pid>/net` rather than assuming ports.

## Troubleshooting

| Symptom | Check |
|---|---|
| `doctor` Steam: not found | Set `TFM_AGENT_STEAM_ROOT` to the directory containing `steamapps/` |
| `doctor` game: not running | Start Transformice from Steam |
| Window not found | Confirm game is up; try `xdotool search --name Transformice` manually (XWayland) |
| Capture: Operation not permitted | `setcap` on venv python (see above); re-run doctor |
| Input does nothing | Window focus; `xdotool` presence; try `--input-backend mock` first to validate wiring |
| ydotool fails | udev/group permissions on `/dev/uinput` |
| Keys stick after crash | Backend `release_all` runs in `finally`; also release manually with arrow-key taps if needed |

## Security constraints (project)

No DLL injection, no process memory reads, no credential/token theft, no binary or SWF patching by default, no anti-cheat bypass, no stealth. Proxy loaders that replace `Transformice.swf` remain opt-in future work requiring explicit consent.
