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

## Verification Scripts
- `pytest` (test)
- `python swarmmojo.py harness` (harness)
- `python swarmmojo.py aeon` (aeon)
- `python swarmmojo.py polyharness build` (polyharness)

## Guardrails
- Protected paths: `.env`, `.git`, `secrets/`
