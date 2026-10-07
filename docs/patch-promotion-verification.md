# Controlled patch apply and rollback — October 5, 2026

T14 adds an operator-controlled promotion workflow on top of real isolated staging and native/container validation. This is an operator CLI increment; broker/model task routing is still unfinished and assistant execution remains disabled. Checkpoint F's model-assisted end-to-end claim is not yet established.

## Operator workflow

After registering a project, staging a proposal and validating its checks:

```sh
goose --review-patch TASK_ID
goose --apply-patch TASK_ID
goose --rollback-patch TASK_ID
```

Apply and rollback display the source repository, base commit, exact patch digest, file existence/content hashes, modes and directional diff. Empty-file creation/deletion and missing final newlines are represented explicitly. Terminal controls in patch content are escaped. Each mutation requires an interactive operator to type the action plus the displayed digest prefix. Piped input, a generic “yes,” missing/expired approval, a different digest, a different purpose, or a wrong token does not authorize mutation. The internal approval capability is bound to the full digest, action and operator UID, expires after ten minutes, is stored only as a hash, and is never printed. Its issuer must never become a model tool.

Each explicit project registration records the repository directory identity and briefly creates/removes a private permission-probe file. The probe records the mode this filesystem can actually provide for new files: this matters on Windows-mounted drives without Linux metadata. Existing-file mode comes from the hashed preimage record. The tested D: drive reports mode 0777 for regular writable files; native Linux storage supports 0644. Validation workers and journals stay on private native Linux storage in both cases.

## Transaction and recovery contract

SwarmMojo additionally compares the patch's bound validation policy version to the current policy before a fresh apply review, authorization or dispatch. A changed policy requires a newly proposed and validated patch. Existing dispatched transactions can still be recovered or rolled back with concrete authorization; this check does not strand interrupted writes. The exact expiry instant is expired. `tests/test_approval_freshness.py` covers these cases using real disposable staging and file transactions with a trusted fixture syntax checker; it does not establish container isolation.

Task and project locks serialize this application's changes. Before writing, promotion verifies the approval, exact validated patch and staging inventory, registered directory identity, current Git HEAD and every touched file's content/mode. No-follow descriptor walks reject substituted symlinks and unsupported target types. Files owned by another UID/GID or carrying exposed extended attributes are refused because this initial policy cannot preserve that metadata; prepared replacements are checked before publication too. A second check immediately before replacing each file catches intervening edits. Unrelated source files and the Git index are not reset or rewritten.

Updates use synchronized same-directory temporary files and per-file replacement. Creation publishes a prepared file through a hard link that cannot overwrite a concurrent new file. Deletion removes only the checked target. Durable intent/completion records and original text/modes support explicit resume or rollback after interruption. Temporary-file identities are recorded before content writing, so a partial temporary write can be cleaned and retried. Created directories are removed on rollback only when their recorded identities still match and they are empty; user additions are retained and reported.

Multi-file apply is journaled, **not globally atomic**. A killed process may leave an applied prefix. Re-run the reviewed apply action to finish, or the reviewed rollback action to reverse it. Conflict detection happens across the whole change set before further writes; a conflicting user edit is preserved. Already completed apply/rollback requests are idempotent and do not overwrite subsequent edits. An interrupted task is not resumed automatically.

The locks coordinate this application, not arbitrary editors. There is a remaining check-to-replacement window against concurrent external or malicious same-user writers; freeze other edits to touched files during promotion. This implementation restores UTF-8 file contents and effective POSIX modes, not original inode identities, timestamps, Windows ACLs, extended attributes or hard-link relationships. An unidentified/replaced temporary file is preserved with an error. A crash between file/directory creation and recording its identity can require manual inspection; recovery never assumes an unknown file or directory is task-owned. Power-loss durability on the Windows drive is not certified by process-crash tests.

## Verification

The fixture suite exercises real Git worktrees and real native/container validation before promotion. It covers a complete mixed edit/create/delete/empty-file roundtrip; unrelated dirty work; missing, stale and mismatched authorization; changed HEAD; touched-file conflicts; replaced project roots; symlink parents; changed validation content; duplicate requests; last-moment user edits; recovery in another process after an apply replacement or partial temporary write; interrupted rollback; preservation of user-added files/directories; no-op recovery; interactive confirmation; exact review rendering; and a roundtrip on the actual D: drive with private Linux journals.

Run the required profile through the installed environment:

```sh
ROMS_LIVE_CONTAINER_IMAGE=sha256:c83674e1999044d33d751661371b873539f47e5b5c5ca3320c7e0377acca6238 \
OMARCHY_NATIVE_WORKER_IMAGE=sha256:7671ccac46e275350fd2d458f755880fb97518db6f117b9cb6ffc346f2bf672d \
python scripts/verify_all.py --containers --sandbox --staging
```

The complete six-group profile passed: 142 Python regressions, 22 compiled broker tests, actual 2.9B/ROMS readiness, nine rootless worker checks, 13 native/combined sandbox checks, and 39 staging/promotion tests (15 staging plus 24 promotion). Live status reported `goose-2.9b`, both services ready and tool execution false. The installed `goose --help` exposes the review/apply/rollback controls. No real user repository was applied or rolled back; all mutation tests used disposable fixtures.

After the final ownership/extended-metadata guard, the complete focused promotion suite passed **25/25** in 60.83 seconds, including native and Windows-drive roundtrips and all crash/approval scenarios. The new metadata case verifies refusal leaves both the original bytes and the extended attribute intact, with no earlier file in the transaction changed. This focused rerun follows the passing full profile; unrelated suites were not repeated.

DEBT(pointdexter): promotion preserves text and POSIX mode only and coordinates cooperative writers; revisit before supporting metadata-rich or shared repositories; upgrade to explicit metadata support and an exclusive workspace service where required. Startup reconciliation and retained-worktree cleanup remain separate lifecycle work.
