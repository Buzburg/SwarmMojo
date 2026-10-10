# Rule: specialized-engines
<!-- Generated automatically by polyharness — DO NOT EDIT DIRECTLY -->

Guidelines for high-speed local agent engines (Symdex, Titans, ToolCall, Sieve, Horizon, Fastgate, Compact-KV, Rewind, PathCarry, LocalDocSearch)

**Applicable Paths**: `app/engines/**/*.py, app_mojo/**/*.mojo`

## Specific Guidelines
- Maintain sub-millisecond execution for in-memory operations and phase vector triage
- Enforce cross-platform path safety and reserved-name audit via PathCarry
- Keep structured working memory preambles bounded (<800 tokens) via Compact-KV
- Maintain native Mojo acceleration in app_mojo/ alongside Python bridges in app/engines/