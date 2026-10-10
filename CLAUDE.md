# CLAUDE.md — Project Guidance for Claude Code
<!-- Generated automatically by polyharness v0.1.0 — DO NOT EDIT DIRECTLY -->

## Project Overview
Full-fledged local-first AI agent harness combining ROMS (RAG, OKF, MCP, Skills), Swarm Mojo (Aeon specialist reviews, workflow rehearsal, mSGL), PolyHarness (universal configuration & deterministic guardrails), and 10 specialized Buzburg engines (Symdex, Titans, ToolCall, Sieve, Horizon, Fastgate, Compact-KV, Rewind, PathCarry, LocalDocSearch).

## Essential Commands
- **test**: `uv run --directory . --with pytest python -m pytest tests/test_engines.py tests/test_swarmmojo.py`
- **harness**: `python swarmmojo.py harness`
- **aeon**: `python swarmmojo.py aeon`
- **polyharness**: `python swarmmojo.py polyharness build`
- **symdex**: `python swarmmojo.py symdex`
- **titans**: `python swarmmojo.py titans`
- **toolcall**: `python swarmmojo.py toolcall`
- **sieve**: `python swarmmojo.py sieve`
- **horizon**: `python swarmmojo.py horizon`
- **fastgate**: `python swarmmojo.py fastgate`
- **compact-kv**: `python swarmmojo.py compact-kv`
- **rewind**: `python swarmmojo.py rewind`
- **path-carry**: `python swarmmojo.py path-carry`

## Core Guidelines & Constraints
- Always run tests before completing changes (pytest)
- Preserve existing comments and docstrings
- Write concise commit messages following Conventional Commits
- Never commit API keys, tokens, or plain secrets
- Keep specialist reviews and decision maker checks bounded and reproducible
- Use PathCarry audits before writing or unpacking files on Windows and cross-platform filesystems

## Safety Boundaries
- **Blocked Commands**: rm -rf /, git push --force, drop database
- **Protected Files**: .env, .git, secrets/

## Active Skills
- **swarm-rehearsal**: Rehearse automation workflows and causal loops
- **polyharness-builder**: Transpiles agent harness configs to all target formats
- **symdex-indexer**: Index and query symbols and call graphs in microsecond latency
- **titans-memory**: Test-time neural memory with momentum and surprise gating
- **sieve-compactor**: Prune repetitive build and test output with 95%+ noise reduction
- **horizon-circuit-breaker**: Track task DAG and intervene on semantic loops
- **rewind-snapshotter**: Content-addressed workspace snapshotting and microsecond rollback
