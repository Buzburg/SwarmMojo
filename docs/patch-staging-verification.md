# Staged patch validation — October 5, 2026

T13's proposed/staged/validating/validated lifecycle is implemented with real isolated Git worktrees and the combined native-container validator. Source checkouts are not modified. Apply, rollback, broker integration and a user-facing approval flow are still separate unfinished work.

## Contract and records

The operator registers an existing local Git repository. Proposals reference that registration ID and a full explicit base commit. A proposal JSON object has exactly `project_id`, `base_commit`, `changes` and `checks`. Each change supplies a canonical relative `path`, `before_sha256` (null for a new file), and complete UTF-8 `after` text (null for deletion). Checks use the registered `python.syntax` or `python.tests` policy.

Limits: 1–32 changes, a 512 KiB complete proposal, 1 MiB per input file, 1–4 checks, and a 32 MiB/2,000-file staging inventory. Symlinks/submodules in the base are rejected in this initial policy. Traversal, control characters, absolute paths, duplicate paths, Git control files, environment/credential paths and agent configuration paths are rejected. Empty text files are supported. A touched-file edit already present in the source checkout conflicts; unrelated user edits are preserved.

The task is bound to a canonical proposal digest, base commit, hashed original-file record and staged file content/mode inventory. Original file text and source permissions are retained. Journal transitions use private temporary files, atomic replacement and file/directory synchronization. A per-task lock prevents concurrent state changes. The task root is `ROMS_DATA_DIR/patches`; the installed build uses the existing private native Linux data location.

Git hooks, fsmonitor, checkout filters and lazy fetching are disabled. Exact registered repositories receive per-command safe-directory handling, without changing global Git configuration. A detached worktree preserves the original branch. Inside workers, the Git pointer file is masked by a read-only empty file so untrusted tests cannot rewrite host worktree metadata. The original pointer remains untouched outside the container mount.

Each check records its real exit status, bounded output and effective policy record. A nonzero check result, cleanup uncertainty or changed staged content prevents `validated`. Even a command that exits zero is rejected if it altered proposed files or file modes. Python bytecode-cache directories are excluded from the comparison and are never proposed promotion content. Patch or preimage record corruption is detected before validation. Failed/cancelled tasks and their isolated worktrees remain available for inspection; automatic stale-task reconciliation is not implemented yet.

## Installed operator commands

```sh
goose --register-project 'D:\path\repository'
goose --stage-patch 'D:\path\proposal.json'
goose --validate-patch TASK_ID
goose --show-patch TASK_ID
goose --patch-tasks
```

Registration and staging are separate from knowledge-library ingestion: one prepares editable project work, while the other adds retrieval snapshots. None of these commands apply changes to the registered source. No repository from the user's supplied folder was automatically registered or modified by the fixture tests.

## Evidence

The full `scripts/verify_all.py --containers --sandbox --staging` profile passed all six required groups: 142 Python regressions, 22 native broker tests, real 2.9B/ROMS readiness, nine container lifecycle/isolation checks, 13 native/combined sandbox checks and 15 staged-patch tests. The installed `goose --patch-tasks` command also completed with an empty user task list.

Staging tests use real repositories with spaces in their paths. They verify a harmless edit through syntax and unittest checks, unchanged source files and unrelated user edits, rejected traversal/control paths, conflicting source edits, patch/preimage digest tampering, syntax failure, forbidden outside writes, protected Git metadata, and a zero-exit test that maliciously modifies the staged source. The latter remains `failed`, with its actual zero exit code and the mutation reason recorded.

DEBT(pointdexter): retained task/worktree cleanup and restart reconciliation are not automatic; revisit before exposing persistent model-driven task execution; upgrade to the transaction recovery and operator cleanup flow. Never delete the original repository as task cleanup.

This checkpoint is not an apply/rollback certification. The next gate must bind concrete authorization to the validated digest, recheck the source revision/preimages immediately before promotion, and journal partial multi-file operations while protecting later user edits.
