# Repair a failed project check

Open the project workshop with `goose --project-workshop` or `/project` in chat. Choose the registered project and files as usual. When a draft fails its registered checks, the workshop displays the recorded diagnostics and task ID. Enter `/repair TASK_ID` to request one model-generated repair of that attempt.

Goose uses the failed draft's selected Python files and a bounded excerpt of the actual recorded failure. It creates a **new staged task** and reruns the original registered checks through the existing private worker. If those pass, the existing review screen shows the exact changes and offers `APPLY` for that patch digest. `UNDO` reviews a separate rollback. Neither repair nor apply starts automatically. Another failed check stops and preserves both attempts.

The initial implementation repairs originally selected, non-test Python files only. It cannot delete a file, select another project or path, edit tests, replace validation commands, approve a patch or apply it. Other changes already in the original proposal are preserved for review. If every proposed change merely restores the original source, it refuses to label that as a new repair. Use the ordinary workshop to intentionally withdraw or redesign a proposal.

Repair requires a failed validation with a nonzero recorded exit status, matching validation-policy records and completed worker cleanup. Missing records, an unsettled worker, a changed stage, a changed source revision or changed selected source bytes prevent repair. Checks repeat after model generation before staging. Parent attempts remain intact; repair records store their task and patch identities, the evidence digest, diagnostic truncation information, model output and resulting child task ID under `ROMS_DATA_DIR/patches/repairs`.

These are local worker journals within the existing trusted-user boundary, not cryptographically authenticated evidence against the operating-system account owner. Callers cannot supply a `succeeded` flag or an arbitrary log through this repair API. Recorded failure text remains untrusted model input and cannot expand permissions.

The 2.9B test-build limits still apply: at most four selected files, 4096 bytes of file contents, a request up to 1024 bytes, measured input up to 3072 tokens and at most 768 generated tokens. The repair excerpt is at most 600 UTF-8 bytes/12 lines; the full recorded output remains in the failed task. Output must be complete and satisfy the existing strict patch schema. Only Python syntax and standard-library unittest checks are registered. Repository staging retains its existing size/type limits. This does not repair arbitrary system services, install missing dependencies or prove correctness beyond the selected checks.

## Verification and limits

An actual 2.9B fixture first demonstrated why syntax alone is insufficient: repairing `VALUE = 2 +` produced `VALUE = 2 + 3`. It passed syntax but failed the required behavior assertion and was **not applied**. This result is retained as a model-quality limitation, not counted as a successful bug fix.

A subsequent behavior-test fixture used `VALUE = 3` with a real confined unittest requiring `2`. The check failed with `3 != 2`; Goose returned exactly `VALUE = 2` with its final newline. The unchanged unittest passed, the reviewed patch applied in the disposable repository, and rollback restored `VALUE = 1`. The test file stayed unchanged. That isolated real-model test passed in 9.30 seconds. An additional actual-worker workshop test confirmed failed syntax → explicit repair → new validation → review, with refusal to apply leaving source untouched.

Offline regressions cover missing/forged record fields, invalid policy paths, unsettled cleanup, changed stage/source/revision/preimages, oversized diagnostics, incomplete/unselected/no-op/deletion proposals, attempted check changes, generation error/cancellation, original attempt preservation and correct original-base hashes. Results qualify these bounded scenarios; they do not certify general autonomous debugging or semantic correctness from syntax checks.

The final combined repair/project-assistant regression run passed 39 tests in 13.28 seconds with the actual validation worker enabled. Its two real-model cases were deliberately deselected; the new real-model behavior-repair case passed separately as described above. No service was restarted or user project changed by these checks.
