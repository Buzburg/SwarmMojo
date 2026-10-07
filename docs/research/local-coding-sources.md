# Local coding sources: useful evidence, no second runtime

Inspected 2026-10-07. Changes apply only to the new SwarmMojo checkout. Original ROMS, the older `swarm-mojo`, local PTRM source and the archives were not modified. The already-built PTRM reviewer was run read-only against selected SwarmMojo source; no installers, builds or model calls were run. All other upstream material was inspected without execution. This is a focused coding-integration review, not a claim that every archive in `D:\Buzburg Files\Harness Repos` was audited.

## Sources checked

| Local source | Identity and license | Code inspected and decision |
| --- | --- | --- |
| `D:\Buzburg Files\HKUDS\ptrm-mojo` | Local PTRM reviewer 0.2; Apache-2.0. No `.git` directory in this checkout, so file hashes below identify the inspected bytes. | `ptrm_reviewer/review.py`, `__main__.py`, `io.py`, `review_worker.mojo`, `REVIEWER.md`, regression-test excerpts. It already emits selected-file hashes, coverage, skipped reasons, finding references and truncation. Reuse that contract in SwarmMojo's existing adapter. No reviewer, planning engine or Triad mutation API copied. |
| `D:\Buzburg Files\Harness Repos\Swarm Mojo` | Earlier Aeon-derived project; Git HEAD `83bbd3b53785cce4305e39692b620ea66d4ebeed`; MIT. Existing README edit and handoff file were left alone. | `aeon/swarm.py`, `tests/test_swarm.py`, `docs/SWARM_REVIEW.md`, `docs/PRECISE_FILES.md`. Its bounded source map declares partial coverage and snapshots observed source. Apply that evidence principle to the existing PTRM adapter; do not import another role scheduler, tool runtime or inference connection. |
| `D:\Buzburg Files\Harness Repos\Final Harness\OpenHarness-main.zip` | Archive identifies HKUDS/OpenHarness; ZIP comment `9b2efd795c6aa09f88b0c257d269a9e518da6ae7`; MIT, OpenHarness Contributors. This archive identity was read locally, not revalidated against GitHub. | README/license; `_parse_verification_entry` and `_run_verification_steps` in `src/openharness/autopilot/service.py`; `tests/test_autopilot/test_verification.py`. It distinguishes parse errors, failed commands and successful exits, with explicit shell opt-in. SwarmMojo already has an operator-owned command catalog, bounded runner, stage validation and exact-patch approval. Keep those instead of adding another verification-policy interpreter or autopilot database. |

Top-level directory listings also located `New Harness`, `Swarmojo`, `Zapier Alt` and other `Final Harness` archives. No feature claims are made for their uninspected contents.

The HKUDS PTRM checkout has no built worker. An existing worker was available in `D:\Buzburg Files\Github\ptrm-mojo\bin\ptrm-review-worker`. Its `review_worker.mojo` and `ptrm/review.mojo` match the inspected HKUDS files byte for byte. Differences in the Python review/transport files were inspected and limited to formatting, typing and equivalent cleanup syntax. The existing GitHub-folder checkout was used for the native smoke check; this does not claim the binary was reproducibly built from those sources. `-B` suppresses Python cache writes in the external checkout. No persistent integration setting was written.

## Adopted small change

[`app/workbench/integrations.py`](../../app/workbench/integrations.py) previously accepted any JSON object and marked it `reviewed`. That could make a successful invocation with every file skipped look like completed coding review. The adapter now validates the existing PTRM report schema, exact selected path set, file/finding source hashes, line ranges, declared truncation, counts and advisory status. It rejects malformed or mismatched evidence and checks the native worker fingerprint before and after review.

The existing workshop sees `partial` for skipped/truncated work and `not_reviewed` when no files were scanned. Reasons remain visible; full findings and per-file skip reasons remain in the report. Unrecognized top-level authority/receipt fields are discarded and normalized advisory flags cannot be overridden by the reviewer. No new package, runtime, database, external command or approval rule was added. File-scan coverage does not measure bugs detected. Fingerprints bind reported bytes and detect observed changes; they do not authenticate an untrusted operator-configured reviewer or prove no transient modification occurred.

The duplicate knapsack implementation in [`prefrontal_cortex.py`](../../app/prefrontal_cortex.py) now re-exports [`context_select.py`](../../app/context_select.py). Valid-input selection, deterministic ties, required records and CLI access remain; both public imports now reject Boolean/non-integer costs, utilities and budgets consistently. The canonical bytearray implementation replaces the duplicate Boolean-list implementation.

## Verification

- Linux/WSL: 74 focused tests passed, covering PTRM report validation, staged-review non-authority, both selector entry points and prefrontal tools. The first run on the Windows-mounted test directory had one existing collector-mode failure; rerunning with Linux `/tmp` storage passed all 74. After independent review tightened rejection of unexpected authority fields, all 29 adapter/integration tests passed again.
- Windows: 45 selector/prefrontal tests passed; the PTRM adapter test module explicitly skips because the existing workshop imports Linux `fcntl`.
- The isolated no-install recovery demo passed. Both module and direct-script selector commands were checked separately.
- The existing native worker then scanned 14 selected changed Python files through the adapter: 14 reviewed, zero skipped, zero rule findings, no declared truncation. The ignored local `data/ptrm-lean-review.json` records the exact reviewed source and worker hashes. Subsequent edits require another review. This demonstrates transport/contract compatibility, not review accuracy or proof of safety.
- Protocol-boundary regressions use synthetic responses. No native worker was rebuilt, upstream suite was run, review-quality benchmark was performed or target-machine performance established.

## SHA-256 evidence

| Source artifact | SHA-256 |
| --- | --- |
| PTRM `ptrm_reviewer/review.py` | `961f381b5bd610bec96d75028a9a8291e4c36de1a0cc2a07d7dbad09a4966799` |
| PTRM `review_worker.mojo` | `f44b21ea8c9b38ac4e831e93f034bb2ca4b03cd5f05e8169866dba696ba1cfc1` |
| PTRM `REVIEWER.md` | `d19adece676abd957925ec2697dd3355bf76c5a2c8da04ea12d453f6a3df6df4` |
| PTRM `LICENSE` | `1a6e2e4bcee14b9f258e6c444747bb44af340c81f980d204e887f6db8662ab3a` |
| Executed GitHub-folder PTRM `ptrm_reviewer/review.py` | `48750f510b87f03635834700225a9c0b45d09d73f737001bdcadb06ea5289143` |
| Executed `bin/ptrm-review-worker` | `8553178234714d7ed113173afb6fb38918ff7f54b43d919fab3b1779553857bc` |
| Earlier Swarm Mojo `aeon/swarm.py` | `62759b2ebed76ba0ccd1f076de5998097ef2bfd5c40f862e465947bf7b3568fa` |
| Earlier Swarm Mojo `tests/test_swarm.py` | `d113a1591fac6b1e9600caf83030a5f6680462ee64adc110a90ac3f1f9018c44` |
| Earlier Swarm Mojo `LICENSE` | `b6b85a40d87ca02b0b07932d6a7009e907cafa8c92db9f27a9bf8b537358afdc` |
| `OpenHarness-main.zip` | `69fceacacf388bc07adb22a2a565aceca4fb85a3bd087f6387416da79097ac91` |
| Archived `src/openharness/autopilot/service.py` | `88519dc50b6151be115b42b150521c4215831a3cb78806cc657cfc89c75327a3` |
