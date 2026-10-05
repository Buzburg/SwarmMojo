---
name: skill_creator
title: Agent Skill Creator Playbook
description: Procedural SOP for designing, architecting, and packaging agent skills from scratch.
---

# Agent Skill Creator Playbook

Use this playbook to design, structure, and scaffold a brand-new skill from scratch.

## When to Use
- When asked to create, design, or implement a new agent capability.
- When creating modular, testable SOPs and tools.

## Protocol
1. **Define Intent & Triggers**:
   - Determine the exact triggers (phrases, user intentions, file types).
   - Formulate clear anti-triggers (when the skill should NOT execute).
2. **Determine Architecture**:
   - Instruction-Only (for standards, reasoning, reviews).
   - CLI / Script-backed (for data processing, API calls, file I/O).
3. **Scaffold Directory**:
   - Target `~/.agents/skills/<skill-name>/` for global access or `.agents/skills/<skill-name>/` for workspace access.
   - Create `SKILL.md` (<500 lines) with YAML frontmatter.
   - Add `scripts/`, `references/`, and `examples/` as required.
4. **Enforce Best Practices**:
   - Prefer stdlib over external dependencies.
   - Always write large outputs to files, never dump raw data to stdout.
   - Implement rate limiting with monotonic clocks and exponential backoff for APIs.
5. **Verify**:
   - Ensure the skill is available as a slash command `/<skill-name>`.
