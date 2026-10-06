# Goose system workshop

Open `goose --system`, type `/system` in Goose chat, or use **Open System Workshop.cmd** in the parent workspace. The installed launcher supplies local authentication. The workshop runs as the ordinary Linux user.

## Available now

| Action | Actual behavior |
|---|---|
| Inspect Goose services | Reads fixed load/active/substate fields for `goose-model`, `goose-roms`, `omarchy-broker` and the user `omarchy-task-worker`. It does not restart services or read private configuration/log contents. |
| List and open an app | Discovers eligible system-installed desktop launchers, shows their names, and opens the operator-selected app through GIO and a separate user systemd unit. |
| Ask Goose | The actual local model proposes service inspection, launching one catalog app, or no supported action. A proposed launch shows the target and requires `OPEN application.desktop` in the interactive terminal. The proposal endpoint performs no operation. |
| Repair project code | Use `/project`, then `/repair TASK_ID` for a recorded failed Python check. See [the repair guide](project-repair.md). |

The OS planner is an authenticated `POST /v1/os/plan` route accepting only an instruction and a bounded catalog of app IDs/names. It uses the pinned local inference service with a catalog-constrained JSON schema, validates the completed result again, and cannot return executable commands, arguments, paths or approvals. Unsupported and ambiguous requests should produce `none`; model correctness still needs evaluation. The client validates the proposal against its original catalog and retains the launcher hash locally.

Read-only automation is available through `python -m scripts.os_workshop --inspect` and `--list-apps` in the configured Linux environment. Operational menu actions require a terminal; piping generated model text into the menu is refused.

## What an application result means

`request_accepted` means the local service manager accepted a launch request. It does **not** prove a visible window, finished startup or successful in-app work. The receipt includes the generated `goose-app-<id>.service` unit and `window_verified: false`.

Timeout, interruption or an unconfirmed command produces `OUTCOME_UNKNOWN` with that unit name. The menu displays a read-only `systemctl --user status -- <unit>` inspection command. There is no automatic retry, persistent launch journal or promise that an interrupted launch did not happen. Save the displayed unit when investigating an uncertain result.

## Current eligibility and environment limits

- Linux, non-root user, verified private user service bus and actual supported local display sockets are required. The first installed test uses WSLg. Native Windows operation is not provided by this adapter.
- The catalog scans at most 2,048 entries and returns at most 32 eligible applications from `/usr/share/applications`. Launchers must be regular root-owned files with trusted, non-writable parent directories and a bounded desktop entry. File names use a restricted ASCII form; names are bounded printable text.
- Hidden/no-display entries, terminal-only entries, D-Bus activation, alternate working directories/desktop restrictions and unrecognized executable forms are excluded. Executables are admitted conservatively from trusted system paths. User-local launchers, portable bundles, Flatpak/Snap discovery and arbitrary command arguments are not implemented in this version.
- GIO interprets desktop-entry launch syntax. The adapter only checks eligibility and rechecks the original file hash immediately before requesting launch. A concurrent administrator/package update can still replace the pathname between that check and GIO opening it. This version does not pin a copied immutable launcher snapshot or defend against the administrator.
- The managed application receives a minimal environment with validated local GUI/bus settings; model API keys and Python/runtime overrides are not forwarded. Loader controls are removed before the clean environment launcher starts. The launched application has the normal user's application permissions; this is not an application sandbox.

The supplied Omarchy WSL environment currently has WSLg but no Hyprland, Quickshell or full desktop session. CMake and Hardware Locality lstopo were eligible; pinentry was excluded as hidden from ordinary app menus. Clicks, typing, accessibility-tree interaction, window focus/close, browser actions, privileged OS repair and Windows application control remain unavailable. The old Mojo desktop dispatcher that only returns success-shaped strings remains disconnected.

## Verification on 6 October 2026

- **54 adapter tests passed**: service selection, bounded output, catalog ownership/types/size, tampering, unsupported GUI/bus, environment handling, launch receipts and uncertain outcomes.
- **94 planner/workshop/doctor tests passed** in the first combined Linux run. The endpoint was exercised with authentication, malformed/oversized input, fabricated targets, incomplete model output, context limits and disconnects. Workshop tests cover exact launch confirmation and preserving the original hash.
- **Actual Goose 2.9B planning and app launch passed**: service-health request selected inspection; an unsupported destructive request selected no action; opening lstopo selected its real catalog ID. A test-owned user unit became active with a nonzero main PID, then was stopped and checked inactive. This established a running GUI application process, not visual window interaction.
- The installed `goose --system` menu was opened through a real terminal. Service inspection returned all four services loaded/active/running, and returning from the menu exited successfully.
- **Integrated verification passed all three groups**: 477 offline tests passed with two explicit live-repair skips; compiled broker checks passed 67 tests plus 13 subtests; the live OS check passed again in 12.50 seconds after the final adapter changes. Real repair/worker checks ran separately and are documented in the repair guide.
- **Expanded Windows CI selection passed 187 tests**, with one host-restricted symlink test skipped. It verifies portable Python interfaces, not Windows OS-control support.

The first live attempt immediately after gateway restart could not connect during startup; it launched nothing. The live fixture now waits for actual model/service readiness before requesting a plan. The current success record is [live-system.json](../../review-artifacts/os-operator/live-system.json); focused logs and JUnit files are beside it. These results are narrow acceptance evidence, not a general claim that a 2.9B model can reliably control every program.

The native GUI actions are based on [GIO application launching](https://docs.gtk.org/gio/iface.AppInfo.html). A later Hyprland adapter must use real [IPC](https://wiki.hypr.land/0.49.0/IPC/) and verify actual effects in an installed session before declaring desktop support.
