# What should enhance SwarmMojo?

Reviewed **2026-10-06**, against the verified ROMS baseline `2d2e207bf2a97c1370971a5e34dbe3bf80ab7348`. The recommendation is a small portable core with selected skills and optional adapters. Combining complete agent runtimes would duplicate state, tools, scheduling and approval systems before demonstrating better results.

The review inspected primary GitHub sources at pinned revisions and local project/download folders on both C: and D:. It did not install or execute the upstream runtimes. Local searches were bounded to likely project and download locations, not a complete scan of every file on either drive. Source inspection establishes implementation details, not model quality, security certification or performance on the future 128 GB machine.

## Included now

SwarmMojo has its own launcher, MCP identity and migration guide. The ROMS knowledge formats, decision engine, MCP compatibility names and approval boundaries remain available. Omarchy is optional.

Three Agency Agents Markdown playbooks are included: **code reviewer, software architect and technical writer**. They are exact upstream text with an immutable revision, SHA-256 records and the original MIT license. They load only when selected and stay outside Decision Maker scoring. Persona claims do not confer experience, memory or permissions. [Imported skills and verification](IMPORTED-SKILLS.md).

No other evaluated runtime was installed, vendored or silently connected. No credentialed service, business action, publication or autonomous worker was enabled.

## Evaluation of every requested project

| Project / resolved identity | What would help | Decision and limit |
| --- | --- | --- |
| [Agency Agents](https://github.com/msitarzewski/agency-agents/tree/5baafd5f1452e9785c413065b033ec083ab27757) | Explicit specialist review and architecture/documentation checklists. | **Included selectively:** three pinned MIT playbooks. The large role catalog is metadata; it is not hundreds of tested independent agents. |
| [Prime Agent](https://github.com/PrimeIntellect-ai/prime-agent/tree/419777a893e8d32bc752085d10320183ff0b6a10) | Separate refinement planning from application; record scope and baseline state. | **Study the proposal pattern.** Keep its Rust runtime and unrestricted execution separate. MIT with retained original attribution; no improvement benchmark was run. |
| [Pi](https://github.com/earendil-works/pi/tree/eb326d265ae0b88489a6d10319307780df827cdf) | Tool lifecycle events, cancellation, branching session records and refusal to execute incomplete tool calls. | **Best next execution-adapter candidate.** Preserve SwarmMojo authorization and confinement. Conversation branching is not a recurrent-model checkpoint. MIT. |
| [Paperclip](https://github.com/paperclipai/paperclip/tree/99a9de9940bf5974352d9dbfbb2f21e62e89689f) | Invocation-time capabilities, business approvals and cost accounting. | **Best business-control reference.** Connect a worker to it if a company dashboard is needed; do not duplicate its server/UI/database in the core. MIT. |
| [Herdr](https://github.com/herdrdev/herdr/tree/a124eed73c1f911ddf89a6ac5b2f7ab70d76f5c2) | Operator console and bounded worker status/read/wait operations. | **Optional console.** Pane control can execute commands, and “done” does not mean verified. Apache-2.0 at the inspected revision; platform behavior untested here. |
| [Nuggets](https://github.com/NeoVertex1/nuggets/tree/714cab8a3b1fb843aa98dfb51584d2c07a6739f3) | Simple user/project/agent memory organization. | **Keep existing lesson storage.** Its recall-count promotion is not correctness evidence and can rewrite existing memory prose. README declares MIT, but a complete license notice was not found; clarify before copying. |
| `e2e` — exact identity unresolved | Potentially structured journeys, outcome proof and ownership-based cleanup. | **Do not integrate an unidentified dependency.** [Agent E2E Harness](https://github.com/aitoroses/agent-e2e-harness/tree/6bb9f145fcf97cdc4b9b7872da1bdc728b1b1a04) is an inspected MIT candidate, not a confirmed match. Unsupported cleanup must remain incomplete, not passed. |
| [AI Engineering from Scratch](https://github.com/rohitg00/ai-engineering-from-scratch/tree/7a181b46332db6d2e1274c798e851bf978a008a9) | Turn corrections into proposed regression tests, rules and examples; compare against a fixed baseline. | **Use as a design workbook.** Its relevant lessons use deterministic toy fixtures and templates; they do not establish production learning or live model gains. MIT. |
| [OpenDots](https://github.com/CopilotKit/OpenDots/tree/625452e06cde74cb25b0ce319e2c1be0488f5a5f) | Persistent review receipts and expected-revision checks for editable business pages. | **Future review UI/reference.** Enforce approval on the server, because a review card alone is not a universal write barrier. Whole-stack adoption adds connected services. MIT. |
| [OpenMuse](https://github.com/CopilotKit/openmuse/tree/1ac68f3909f2478ab6280883f1ab5ea65eb5719d) | Digest-bound actions, expiry, account checks, worker leases and uncertain-outcome tracking. | **Strong external-action lifecycle reference.** Local archive confirms CopilotKit identity. Whole platform requires an Intelligence key; its optional OpenBot adapter is disabled and tied to an older contract. MIT. |
| `openbot` — [CopilotKit/OpenBot](https://github.com/CopilotKit/OpenBot/tree/17831b2415b3f764cdb07110ca68fdab18fe8b2d) is the assessed candidate | Consume approval before dispatch, recheck actor/digest, preserve unknown outcomes after interruption. | **Reference, not yet a confirmed name match.** Chosen because the locally identified OpenMuse integrates with it. Other OpenBot projects differ; no runtime was adopted. MIT. |
| [OpenClaw](https://github.com/openclaw/openclaw/tree/078ca8950dbcb65b47d74a494b64f5aed8376180) | Explain which policy layer blocked a tool; later add authenticated channel ingress. | **Defer the gateway.** It overlaps conversation, tools, skills and scheduling. Tool restrictions and sandbox placement remain separate concerns. MIT. |

Exact implementation files, license evidence, name ambiguity and acceptance cases are in the [orchestration review](research/orchestration.md), [learning/workspace review](research/learning-evaluation.md) and [runtime review](research/runtime-platforms.md).

## Related harnesses worth evaluating

- **[Goose](https://github.com/aaif-goose/goose/tree/f9c18a81952e8895b6f2d88b0f4569f3975034af), Apache-2.0:** an external MCP consumer is a smaller integration than embedding its runtime. Client Auto/SmartApprove settings cannot satisfy SwarmMojo authorization. A real pinned-client handshake is still required before advertising interoperability.
- **[Deep Agents](https://github.com/langchain-ai/deepagents/tree/16e84d927e7e13c41a10c071380c875af6a562f5), MIT:** useful bounded specialist contexts and checkpoint patterns. Child/remote permissions require explicit policy; they do not automatically inherit every parent guard. Add an adapter only for a concrete consumer.
- **[Nanobot](https://github.com/HKUDS/nanobot/tree/d6ddceed997b53c4adcd56e8b302bd124bfa0c71), MIT:** recovery cases that retain completed observations and mark unfinished calls interrupted. Reuse the scenarios before adding another scheduler or session store.

## Recommended next build order

1. **Measure the selected skills.** Use representative coding/documentation tasks with and without each playbook. Track verified success, recurring failures, context size, elapsed time and abstention. Keep failures and timeouts in the denominator; current tests prove integration boundaries, not improved model quality.
2. **Add a correction-to-regression proposal queue.** Reuse existing scoped lessons and the validator. Record source run/revision, observed failure, proposed test or inactive skill draft, validation result and review status. Repeated retrieval may rank a proposal, never activate it.
3. **Choose one external worker, probably Pi or Goose.** Qualify event/schema handling, cancellation, incomplete responses, duplicate and late results, replay, bounded output and revoked approval. Retain full original transcripts separately from compacted context.
4. **Add a business connector with durable approval records.** Combine existing promotion principles with Paperclip/OpenMuse/OpenBot/OpenDots patterns. Bind actor/account, exact arguments, target revision, adapter, policy version and expiry. An uncertain remote outcome must be reconciled before retrying; a worker lease alone cannot guarantee exactly-once remote effects.
5. **Add UI, console and channel adapters afterward.** Website edits, invoices and calendar changes need observable outcomes and exact approvals. Herdr/OpenClaw and richer interfaces stay optional. Test against development accounts before enabling real effects.

## Local findings and preserved work

The original ROMS checkout and both older Swarm-related folders were left intact. The pre-existing private `Buzburg/swarm-mojo` is a different project at `83bbd3b53785cce4305e39692b620ea66d4ebeed`, with unfinished local work. New **`Buzburg/SwarmMojo`** has its own directory, remote and history continuation from the verified ROMS baseline.

Local evidence included an Agency import with hashes but no verified upstream commit; a `paperclip` folder that is actually a memory adapter; an exact 83-file Nuggets archive match; the CopilotKit OpenMuse archive; an older Nanobot archive; and a separate unversioned Swarmojo research collection whose referenced `gsh_core` is absent. The AI Engineering archive found in C: Downloads carries the same `7a181b46…` commit as the inspected upstream. Archive names alone were never treated as identity or proof of working integration.

ROMS is private. The new repository is also private while integration is evaluated. Repository visibility, branding and source inclusion do not change the execution approval rules.
