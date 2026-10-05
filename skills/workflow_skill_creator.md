---
name: workflow_skill_creator
title: Workflow Skill Creator Playbook
description: Procedural SOP for distilling a completed conversation or workflow into a reusable agent skill.
---

# Workflow to Skill Creator Playbook

Use this playbook to convert a multi-step workflow that just happened into a reusable agent skill.

## When to Use
- When the user says "make this a skill", "package this workflow", or "turn what we just did into a skill".
- When an existing series of manual steps should be codified into an automated protocol.

## Protocol
1. **Analyze Prior Turns**:
   - Extract the core sequence of operations, commands run, and APIs queried.
   - Separate input parameters from hardcoded values.
2. **Brainstorming with User**:
   - Confirm workflow scope, expected inputs, outputs, and rigidity (strict vs. flexible steps).
   - Identify which existing skills can be reused rather than reimplemented.
3. **Select Pattern**:
   - CLI Pattern (if API calls, data transformation, or file I/O occurred).
   - Instruction Pattern (if purely multi-step reasoning or tool coordination).
4. **Package & Install**:
   - Write `SKILL.md` following standard frontmatter.
   - If CLI pattern, write Python helper scripts with `argparse`, file outputs, and error handling.
   - Install to global (`~/.agents/skills/`) or workspace (`.agents/skills/`).
5. **Verify**:
   - Test execution against sample input and verify slash command `/<skill-name>` readiness.
