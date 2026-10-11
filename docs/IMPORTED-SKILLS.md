# Compact specialist playbooks

Swarmojo includes concise specialist review and architecture playbooks by Buzburg AI. The [source manifest](../config/skill_sources.json) tracks file byte counts and checksums.

| Skill name | Intended use | Input size |
| --- | --- | --- |
| `agency-code-reviewer` | Review correctness, security and tests; report actionable findings. | 1,276 bytes |
| `agency-software-architect` | Compare designs, define boundaries and record tradeoffs. | 1,293 bytes |
| `agency-technical-writer` | Explain a reproducible workflow and its actual limits. | 1,259 bytes |

The three files total **3,828 bytes**, down from 23,775 bytes of imported prose (83.9% smaller). Repeated persona, fictional memory and experience claims, long templates, and illustrative examples were removed. Existing skill names remain compatible.

Select them in a harness request's `skills` array, or read them through MCP `skills://{skill_name}`. The [review example](../examples/code-review-request.json) loads the small review playbook. It supplies example observations rather than inspecting a real project; replace them with your actual evidence.

These checklists are untrusted context, not trained agents, execution capabilities or factual evidence. Swarmojo keeps their content outside decision scoring. They do not broaden the operator's instructions or grant permission to change, execute or publish anything.

The shared context budget applies. A long playbook can be truncated or omitted when evidence and retrieved excerpts consume the budget; inspect `context.coverage`. Select one relevant role at a time, preserve source references and evaluate its usefulness on representative tasks before expanding the collection.

The old role catalog remains metadata only. These adapted files are actually readable by the harness. No automatic upstream updates, package installation, agent loop or external service was added.

CI verifies local file/license hashes, distinct upstream provenance, compact size limits, actual selection through the harness and that skill text cannot become evidence or approval. All three fit the default context budget when no other text consumes it; smaller budgets still report truncation. This establishes reduced input size, not better model answers, which require a live-model comparison.
