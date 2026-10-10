# CLAUDE.md — Project Guidance for Claude Code
<!-- Generated automatically by polyharness v0.1.0 — DO NOT EDIT DIRECTLY -->

## Project Overview
Full-fledged local-first AI agent harness combining ROMS (RAG, OKF, MCP, Skills), Swarm Mojo (Aeon specialist reviews, workflow rehearsal, mSGL), and PolyHarness (universal configuration & deterministic guardrails).

## Essential Commands
- **test**: `pytest`
- **harness**: `python swarmmojo.py harness`
- **aeon**: `python swarmmojo.py aeon`
- **polyharness**: `python swarmmojo.py polyharness build`

## Core Guidelines & Constraints
- Always run tests before completing changes (pytest)
- Preserve existing comments and docstrings
- Write concise commit messages following Conventional Commits
- Never commit API keys, tokens, or plain secrets
- Keep specialist reviews and decision maker checks bounded and reproducible

## Safety Boundaries
- **Blocked Commands**: rm -rf /, git push --force, drop database
- **Protected Files**: .env, .git, secrets/

## Active Skills
- **swarm-rehearsal**: Rehearse automation workflows and causal loops
- **polyharness-builder**: Transpiles agent harness configs to all target formats
