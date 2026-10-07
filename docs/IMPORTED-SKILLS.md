# Source-verified specialist playbooks

SwarmMojo includes three explicitly selected Markdown playbooks from [Agency Agents](https://github.com/msitarzewski/agency-agents/tree/5baafd5f1452e9785c413065b033ec083ab27757). The exact upstream bytes, MIT license and content hashes are retained; see [the source manifest](../config/skill_sources.json) and [license](../third_party/agency-agents/LICENSE).

| Skill name | Intended use | Input size |
| --- | --- | --- |
| `agency-code-reviewer` | Structured review of correctness, security, maintainability and tests. | 3,076 bytes |
| `agency-software-architect` | State design tradeoffs and prepare architecture decision records. | 6,485 bytes |
| `agency-technical-writer` | Improve quickstarts, examples and documentation structure. | 14,214 bytes |

Select them in a harness request's `skills` array, or read them through MCP `skills://{skill_name}`. The [review example](../examples/code-review-request.json) loads the small review playbook. It supplies example observations rather than inspecting a real project; replace them with your actual evidence.

These are untrusted prompt templates, not trained agents, execution capabilities or factual evidence. Fictional identity, memory and experience claims in the preserved upstream text are role-playing instructions only. They do not describe the runtime. SwarmMojo keeps their content outside decision scoring and still requires separate approval for every proposed action.

The shared context budget applies. A long playbook can be truncated or omitted when evidence and retrieved excerpts consume the budget; inspect `context.coverage`. Select one relevant role at a time, preserve source references and evaluate its usefulness on representative tasks before expanding the collection.

The old role catalog remains metadata only. These imported files are distinct, source-pinned playbooks actually readable by the harness. No automatic upstream updates, package installation, agent loop or external service was added.

CI verifies file/license hashes, Markdown size limits, actual selection through the harness and that skill text cannot become evidence or approval. It does not establish better model answers; that requires a live-model comparison with and without the selected playbook.
