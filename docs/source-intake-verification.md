# Source library increment — October 5, 2026

The installed Goose 2.9B test build now accepts local text files, tracked Git checkout files and text folders into ROMS. A terminal menu is available through the workspace's `Open Knowledge Library.cmd` launcher or `goose --library`. Source ingestion changes retrieval memory only. Training remains deferred.

## Evidence

- Full WSL verification after menu/readiness changes: 130 Python regressions, 22 compiled-broker tests, and live model/ROMS readiness passed (3/3 required groups). Reported model: `goose-2.9b`.
- Final targeted source-library suite after bounding Git output: 7 passed. This adds one test to the previous full inventory.
- Installed menu smoke: list and exit succeeded; no user sources were added.
- `scripts/check_source_intake.py`: installed CLI imported two disposable repositories using real MiniLM embeddings; both same-name README files were independently retrieved. Removing the sources invalidated search results in a separate long-lived process and preserved edited original files. Temporary indexed sources were removed.
- Windows-path preview through the installed launcher succeeded for the existing refund-policy Markdown file without importing it.

The first full verifier run failed live readiness because WSL had cold-started and the services were loading. The verifier now polls for up to 90 seconds and still fails if either service stays unavailable. Dedicated tests cover delayed success and the deadline failure. The subsequent full run passed.

## Review and limits

Correctness: explicit document identity fixes cross-repository basename collisions. Existing ingestion callers retain their original identity behavior. Each import owns an independent namespace; removal queries that namespace rather than trusting document IDs from a manifest. Failure cleanup preserves other sources.

Security: imported code is never executed. Files are opened through pinned directory descriptors without following repository symlinks. Git hooks/fsmonitor are disabled for listing; global/system Git configuration is excluded. The listing has a 15-second deadline and 4 MiB output cap. Private directories contain snapshots. Exclusion rules cover common secrets and generated files, but do not guarantee detection of secrets embedded in otherwise ordinary text.

Architecture/performance: reuse the existing embedding and SQLite ingestion paths, with no new dependency or model change. Admission limits constrain file counts/bytes and folder enumeration. The menu and CLI operate in the existing Linux runtime. Cross-process SQLite change detection already present in retrieval was verified against real CLI writes.

DEBT(pointdexter): imports commit per document and a forced interruption can leave a partial `indexing` source; revisit before concurrent bulk imports; upgrade to a recoverable collection transaction or explicit startup reconciliation. Users can currently remove or refresh the source.

DEBT(pointdexter): repeated imports of the same origin create independent copies; revisit when adding bulk synchronization; upgrade to manifest-aware deduplication. Use refresh to replace an existing source.

PDF/Office parsing, remote repository cloning, graphical file picking and model training are outside this delivered increment. The original roadmap remains partially implemented; these checks do not certify autonomous execution, native desktop operation, patch apply/rollback or recurrent checkpoint persistence.
