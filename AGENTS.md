# AGENTS.md
<!-- Generated automatically by polyharness v0.1.0 — DO NOT EDIT DIRECTLY -->

## Repository Identity
- **Name**: SwarmMojo
- **Version**: 1.0.0
- **Primary Stack**: python (fastmcp)

## Agent Rules of Engagement
- Always run tests before completing changes (pytest)
- Preserve existing comments and docstrings
- Write concise commit messages following Conventional Commits
- Never commit API keys, tokens, or plain secrets
- Keep specialist reviews and decision maker checks bounded and reproducible
- Use PathCarry audits before writing or unpacking files on Windows and cross-platform filesystems

## Verification Scripts
- `uv run --directory . --with pytest python -m pytest tests/test_engines.py tests/test_swarmmojo.py` (test)
- `python swarmmojo.py harness` (harness)
- `python swarmmojo.py aeon` (aeon)
- `python swarmmojo.py polyharness build` (polyharness)
- `python swarmmojo.py symdex` (symdex)
- `python swarmmojo.py titans` (titans)
- `python swarmmojo.py toolcall` (toolcall)
- `python swarmmojo.py sieve` (sieve)
- `python swarmmojo.py horizon` (horizon)
- `python swarmmojo.py fastgate` (fastgate)
- `python swarmmojo.py compact-kv` (compact-kv)
- `python swarmmojo.py rewind` (rewind)
- `python swarmmojo.py path-carry` (path-carry)
- `python swarmmojo.py drift` (drift)
- `python swarmmojo.py statefresh` (statefresh)
- `python swarmmojo.py workflowproof` (workflowproof)
- `python swarmmojo.py cortex` (cortex)
- `python swarmmojo.py triad` (triad)
- `python swarmmojo.py mojo-memory` (mojo-memory)
- `python swarmmojo.py studio` (studio)
- `python swarmmojo.py design` (design)
- `python swarmmojo.py meta` (meta)

## Guardrails
- Protected paths: `.env`, `.git`, `secrets/`
