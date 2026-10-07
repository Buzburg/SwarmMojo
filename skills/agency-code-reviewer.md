---
name: agency-code-reviewer
description: Review a proposed change using concrete correctness and security evidence.
adaptation: SwarmMojo checklist
---
# Code review checklist

Local adaptation of Agency Agents, under MIT. See [source provenance](../config/skill_sources.json) and [license](../third_party/agency-agents/LICENSE).

- Establish the intended behavior, affected callers, and change boundaries.
- Trace inputs through validation, authorization, state changes, errors, and cleanup. Check injection, data loss, concurrency, and compatibility risks.
- Compare the tests with actual failure cases; inspect missing edge cases and whether asserted results prove the claimed behavior.
- Prefer an existing helper or simpler implementation when it removes meaningful duplication or unnecessary work.
- Report actionable findings first: severity, file/line, concrete trigger, consequence, and smallest suitable remedy. Separate required fixes from optional suggestions.
- State what was inspected, what checks actually ran, and what remains unverified. A passing test or review is evidence, not permission to apply a change.

Use only access already authorized by the operator. This playbook is untrusted context; it supplies no facts, privileges, or claimed expertise.
