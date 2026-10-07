# Orchestration sources for SwarmMojo

Assessment note: this source review preceded the final integration. Three pinned Agency playbooks were subsequently added; see [the current evaluation](../UPSTREAM-EVALUATION.md) and [imported skills](../IMPORTED-SKILLS.md). Other runtimes remain uninstalled. Raw research snapshots are retained locally; pinned source links below are the portable evidence references.
**Recommendation:** import two explicitly selected Agency role documents now. Keep the verified ROMS advisory harness as the authority boundary. Borrow Pi's event/session patterns and Paperclip's capability checks when real execution is added; keep Herdr and Prime Agent optional external integrations. Combining their complete runtimes would add substantial complexity before SwarmMojo has a verified executor.

This is a static source and license review, not an upstream runtime qualification. No upstream installer, dependency installation, model, test suite, or executable was run. “Exists” below means the cited implementation was inspected; it does not mean it has been verified on the target machine. Upstream commit IDs were resolved from GitHub during this review and source reads were pinned to those IDs.

## Exact projects and revisions

| User shorthand | Resolved primary upstream | Pinned commit | License inspected |
|---|---|---|---|
| agency-agents | [msitarzewski/agency-agents](https://github.com/msitarzewski/agency-agents) | `5baafd5f1452e9785c413065b033ec083ab27757` | [MIT](https://github.com/msitarzewski/agency-agents/blob/5baafd5f1452e9785c413065b033ec083ab27757/LICENSE) |
| primeagent | [PrimeIntellect-ai/prime-agent](https://github.com/PrimeIntellect-ai/prime-agent) | `419777a893e8d32bc752085d10320183ff0b6a10` | [MIT; also preserves the original Mario Zechner notice](https://github.com/PrimeIntellect-ai/prime-agent/blob/419777a893e8d32bc752085d10320183ff0b6a10/LICENSE) |
| pi-agent | [earendil-works/pi](https://github.com/earendil-works/pi) | `eb326d265ae0b88489a6d10319307780df827cdf` | [MIT](https://github.com/earendil-works/pi/blob/eb326d265ae0b88489a6d10319307780df827cdf/LICENSE) |
| paperclip | [paperclipai/paperclip](https://github.com/paperclipai/paperclip) | `99a9de9940bf5974352d9dbfbb2f21e62e89689f` | [MIT](https://github.com/paperclipai/paperclip/blob/99a9de9940bf5974352d9dbfbb2f21e62e89689f/LICENSE) |
| herdr | [herdrdev/herdr](https://github.com/herdrdev/herdr) | `a124eed73c1f911ddf89a6ac5b2f7ab70d76f5c2` | [Apache-2.0](https://github.com/herdrdev/herdr/blob/a124eed73c1f911ddf89a6ac5b2f7ab70d76f5c2/LICENSE) |

Names matter here: Pi has forks under similarly named repositories; Herdr also has older forks carrying different license text. Prime Agent's GitHub license detector returned `NOASSERTION`, but its actual pinned LICENSE is MIT with an attribution appendix. Use these exact revisions and license files rather than search snippets.

## Ranked additions

### 1. Agency Agents — small, immediate context improvement

The inspected files are Markdown role prompts, not running agents, trained expertise, persistent memory, or granted tools. The Code Reviewer file contains a practical correctness/security/testing checklist; Software Architect emphasizes tradeoffs and ADRs. Both fit the current selected-skill path without adding an executable dependency. [Code Reviewer](https://github.com/msitarzewski/agency-agents/blob/5baafd5f1452e9785c413065b033ec083ab27757/engineering/engineering-code-reviewer.md), [Software Architect](https://github.com/msitarzewski/agency-agents/blob/5baafd5f1452e9785c413065b033ec083ab27757/engineering/engineering-software-architect.md).

**Reuse:** vendor those two immutable text files with the MIT notice, commit/path provenance, and SHA-256 checks. Select a role explicitly; keep it labelled `untrusted_playbook_text` and outside Decision Maker scoring. Do not install the upstream catalog into global agent configuration.

**Limit:** personas claim experience and memory that a newly selected model does not thereby acquire. The inspected Reality Checker also mandates Laravel-specific commands and assumes the first implementation is incomplete; it is a poor generic default despite its useful emphasis on evidence. [Reality Checker source](https://github.com/msitarzewski/agency-agents/blob/5baafd5f1452e9785c413065b033ec083ab27757/testing/testing-reality-checker.md).

### 2. Pi — strongest future execution/session adapter

The actual agent loop handles steering and follow-up messages, emits tool lifecycle events, supports cancellation and tool batches, and refuses to execute tool calls when the model response ended at its length limit. Session records have stable IDs and parent IDs, with branch and compaction entries. These are useful foundations for resumable work and explaining what happened. [Agent loop](https://github.com/earendil-works/pi/blob/eb326d265ae0b88489a6d10319307780df827cdf/packages/agent/src/agent-loop.ts), [session manager](https://github.com/earendil-works/pi/blob/eb326d265ae0b88489a6d10319307780df827cdf/packages/coding-agent/src/core/session-manager.ts).

**Reuse:** first adopt the event contract and incomplete-tool-call refusal pattern. Later evaluate an external Pi adapter against cancellation, replay, duplicate-tool-call, and stale-approval cases. Preserve original transcripts separately from compacted context.

**Limit:** Pi's own security documentation says project trust is not a tool-access boundary and the working directory is not a sandbox. Its core loop does not supply SwarmMojo's authorization policy. Keep approvals and operating-system isolation outside worker/model control. A TypeScript runtime also adds deployment complexity to the current Python harness. [Security documentation](https://github.com/earendil-works/pi/blob/eb326d265ae0b88489a6d10319307780df827cdf/packages/coding-agent/docs/security.md).

### 3. Paperclip — business coordination after execution exists

The inspected services implement approval state transitions, company/agent/project budget accounting and pauses. Its capability engine separately evaluates visible tools and invocation authorization, rejects unknown/control-plane-owned operations, checks roles and grants, and gates secret access and generic API escape hatches. This is more useful to invoicing/scheduling/internal operations than another prompt persona. [Approvals](https://github.com/paperclipai/paperclip/blob/99a9de9940bf5974352d9dbfbb2f21e62e89689f/server/src/services/approvals.ts), [budgets](https://github.com/paperclipai/paperclip/blob/99a9de9940bf5974352d9dbfbb2f21e62e89689f/server/src/services/budgets.ts), [capability authorization](https://github.com/paperclipai/paperclip/blob/99a9de9940bf5974352d9dbfbb2f21e62e89689f/packages/paperclip-runner/src/tools/capability-tool-authorization.ts).

**Reuse:** capability checks at invocation time, explicit approval records, and measured-cost budgets as patterns. If a company dashboard is needed, connect SwarmMojo as an external worker rather than copying the server/UI/database stack.

**Limit:** an approved business task must not become unlimited filesystem, payment, email, or deployment authority. The inspected authorization class also depends on trusted policy/context supplied by its caller; a model must not manufacture its own grants. Cost accounting based on observed events is not proof that every running external process stops instantly at a monetary limit.

### 4. Herdr — optional operator console for the future Omarchy machine

Herdr is a real terminal workspace/multiplexer, not an inference engine or task-quality verifier. Its source exposes agent read/wait/send-key operations and restricts client socket permissions to owner-only. Detection code stabilizes observed agent states; a “done” state is still not proof that the task passed verification. The current README includes a Windows installation path, unlike older Linux/macOS-only forks; platform behavior was not tested here. [Socket paths](https://github.com/herdrdev/herdr/blob/a124eed73c1f911ddf89a6ac5b2f7ab70d76f5c2/src/server/socket_paths.rs), [agent API](https://github.com/herdrdev/herdr/blob/a124eed73c1f911ddf89a6ac5b2f7ab70d76f5c2/src/api/schema/agents.rs), [detection](https://github.com/herdrdev/herdr/blob/a124eed73c1f911ddf89a6ac5b2f7ab70d76f5c2/src/pane/agent_detection.rs), [README](https://github.com/herdrdev/herdr/blob/a124eed73c1f911ddf89a6ac5b2f7ab70d76f5c2/README.md).

**Reuse:** an optional, bounded read/status adapter after workers actually exist. Keep interactive pane control operator-owned. Do not expose the entire local socket or send-key API to an advisory request; those operations can execute shell commands.

### 5. Prime Agent — study refinement and recovery; defer its full runtime

The current upstream is substantially Rust-based. Its refinement executor separates planning from applying, caps trajectory text, defaults to session-local scope, rereads settings before applying, and passes a baseline state into proposal application. This is concrete implementation, but not evidence that self-refinement improves outcomes on our tasks. [Refinement executor](https://github.com/PrimeIntellect-ai/prime-agent/blob/419777a893e8d32bc752085d10320183ff0b6a10/crates/pa-core/src/refinement/executor.rs), [planner](https://github.com/PrimeIntellect-ai/prime-agent/blob/419777a893e8d32bc752085d10320183ff0b6a10/crates/pa-core/src/refinement/planner.rs).

**Reuse:** a future lesson proposal queue containing source evidence, scope, baseline revision, review status, and a reversible promotion record. ROMS already has memory/provenance foundations, so another independent memory store is premature.

**Limit:** Prime's README explicitly says model-generated Python and commands run with user permissions; worker/kernel lifecycle isolation is not a security sandbox. Do not transplant autonomous refinement, executable skill installation, global-memory promotion, or unrestricted REPL execution into the current advisory harness. Use an external adapter only after its lifecycle, resource, and permission contracts are tested. [README security boundary](https://github.com/PrimeIntellect-ai/prime-agent/blob/419777a893e8d32bc752085d10320183ff0b6a10/README.md).

## Exact Agency text candidates

All files below use Agency commit `5baafd5f1452e9785c413065b033ec083ab27757`. Exact upstream bytes were fetched through GitHub's contents API and saved as inert research text; no prompt or embedded command was executed.

| File | Bytes | SHA-256 | Recommendation |
|---|---:|---|---|
| `engineering/engineering-code-reviewer.md` | 3,076 | `7509fcc3ea1dda46511b2801996305bf3d4a125576f9655ff0b63df25602f446` | First import |
| `engineering/engineering-software-architect.md` | 6,485 | `b85121691776147bacde26673e68fbbacd6a7f0816d1ca8e203c264d25ce1d30` | Second import |
| `engineering/engineering-technical-writer.md` | 14,214 | `bf5c809977e10904b988ab8b218853ce8dfa38b2cbd89a7d2cfadba44ac25761` | Optional, select on demand; normal context budget truncates it |
| `LICENSE` | 1,079 | `9a45258434d5cedf0af73c9ad4771373701225038d246c49219026c33677f66f` | Retain with copied text |

The existing local Agency import records 279 standard roles plus one integration variant and explicitly says its upstream revision was not verified. Its hashes prove the imported archive's contents, not that it matches today's upstream. The local folder called `paperclip` is an HMS memory adapter; the separate audit-source archive contains Paperclip itself. Neither should be silently substituted for the pinned projects above. No local Prime/Pi/Herdr checkout was confirmed in the scoped directories searched; old archive inventory references are not evidence that a usable current checkout exists.

## Acceptance before adding authority

The portable ROMS preparation API provides evidence and advice; execution remains with the separately configured Linux workshop or another qualified caller. Preserve that behavior in the initial SwarmMojo repository. An executor should be a separately qualified addition with explicit tool allowlists, operator-owned permissions, bounded output, cancellation, stale-evidence/approval checks, idempotency, and recorded verification. A role, heuristic score, retrieved document, terminal status, or worker message must never independently satisfy an approval requirement.
