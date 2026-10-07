# Learning, evaluation and workspace references for SwarmMojo

Assessment note: this source review preceded the final integration. Three pinned Agency playbooks were subsequently added; see [the current evaluation](../UPSTREAM-EVALUATION.md) and [imported skills](../IMPORTED-SKILLS.md). Other runtimes remain uninstalled. Raw research snapshots are retained locally; pinned source links below are the portable evidence references.

Additional local evidence: the AI Engineering archive in the C: Downloads folder carries upstream commit `7a181b46332db6d2e1274c798e851bf978a008a9`; the archive was not executed.

Reviewed 2026-10-06. This is a source inspection, not an installation, benchmark or security certification. No upstream programs, setup scripts or tests were executed. Comparison baseline: ROMS at `2d2e207bf2a97c1370971a5e34dbe3bf80ab7348`; the SwarmMojo identity does not change these implementation boundaries.

## Identity and provenance

| Requested name | Verified identity and source commit | License found | Status |
| --- | --- | --- | --- |
| nuggets | [NeoVertex1/nuggets](https://github.com/NeoVertex1/nuggets/tree/714cab8a3b1fb843aa98dfb51584d2c07a6739f3), `714cab8a3b1fb843aa98dfb51584d2c07a6739f3` | [README declares MIT](https://github.com/NeoVertex1/nuggets/blob/714cab8a3b1fb843aa98dfb51584d2c07a6739f3/README.md#license); no LICENSE text/copyright notice file was found, and GitHub license metadata is null. | Local `HKUDS/nuggets-main.zip` matches all 83 upstream Git blob hashes. Archive SHA-256: `db6bf7df49e7942432d22f21d750b694bab143b46373a70ca02c1e9857744726`. Confirm the intended license notice before vendoring. |
| rohitg00/ai-engineering-from-scratch | [Exact requested repository](https://github.com/rohitg00/ai-engineering-from-scratch/tree/7a181b46332db6d2e1274c798e851bf978a008a9), `7a181b46332db6d2e1274c798e851bf978a008a9` | [MIT, Rohit Ghumare](https://github.com/rohitg00/ai-engineering-from-scratch/blob/7a181b46332db6d2e1274c798e851bf978a008a9/LICENSE). | Curriculum with executable lesson examples; not a complete agent runtime. |
| opendots | [CopilotKit/OpenDots](https://github.com/CopilotKit/OpenDots/tree/625452e06cde74cb25b0ce319e2c1be0488f5a5f), `625452e06cde74cb25b0ce319e2c1be0488f5a5f` | [MIT, Atai Barkai](https://github.com/CopilotKit/OpenDots/blob/625452e06cde74cb25b0ce319e2c1be0488f5a5f/LICENSE). | The canonical repository identified by its own documentation; a workspace application template with separately configured services. |
| e2e | **Unresolved requested identity.** Relevant candidate: [aitoroses/agent-e2e-harness](https://github.com/aitoroses/agent-e2e-harness/tree/6bb9f145fcf97cdc4b9b7872da1bdc728b1b1a04), `6bb9f145fcf97cdc4b9b7872da1bdc728b1b1a04`. | Candidate [MIT, Aitor Roses](https://github.com/aitoroses/agent-e2e-harness/blob/6bb9f145fcf97cdc4b9b7872da1bdc728b1b1a04/LICENSE). | No exact local repository or supplied owner/URL establishes that this is the user's “e2e.” Assessment below is conditional, not identification. |

Pinned source-file indexes and selected source files are retained in `source-metadata/` for this local review. They are research material, not newly adopted dependencies or a redistribution bundle. Preserve original notices if MIT-licensed code is subsequently reused.

## Nuggets: useful organization, unsuitable automatic promotion

Actual implementation: topic/kind-specific JSON stores retain the original key/value facts. Complex-vector binding and decoding sit behind key, substring and word-overlap resolution. This is an associative lookup experiment, not learned language-model weights or a saved recurrent inference state. [Memory implementation](https://github.com/NeoVertex1/nuggets/blob/714cab8a3b1fb843aa98dfb51584d2c07a6739f3/src/nuggets/memory.ts), [numerical primitives](https://github.com/NeoVertex1/nuggets/blob/714cab8a3b1fb843aa98dfb51584d2c07a6739f3/src/nuggets/core.ts).

The promotion path writes facts with at least three hits into the agent's `MEMORY.md`. Hits measure recall, not correctness. Only the last session ID is retained, so alternating session IDs can count again; updating a fact preserves its prior hit count. Its Markdown reader retains recognized section/fact lines and re-renders the file, so other existing prose can disappear. Atomic rename does not resolve concurrent writers or these semantic issues. [Promotion code](https://github.com/NeoVertex1/nuggets/blob/714cab8a3b1fb843aa98dfb51584d2c07a6739f3/src/nuggets/promote.ts).

**Reuse selectively:** the clear distinction between user, project and agent memory is a useful interface idea. SwarmMojo already has scoped candidate/verified lessons, corrections and retractions in [memory.py](../../app/memory.py); keep that store. Do not equate popularity with verification or replace provenance with holographic scores; resolve the incomplete license notice before importing code. The inspected [tests](https://github.com/NeoVertex1/nuggets/blob/714cab8a3b1fb843aa98dfb51584d2c07a6739f3/tests/memory.test.ts) exercise toy recall and persistence, not representative coding improvements.

## AI Engineering from Scratch: a design workbook, not an engine

The useful lesson is converting a correction into a durable control: a regression test, scope rule, preflight or example, retaining the original symptom/cause and deduplicating a proposed control by fingerprint. Its actual implementation is keyword classification and text-template output; the produced verification instructions do not themselves execute a new test. [Lesson 46 implementation and tests](https://github.com/rohitg00/ai-engineering-from-scratch/tree/7a181b46332db6d2e1274c798e851bf978a008a9/phases/14-agent-engineering/46-turn-feedback-into-system/code).

The evaluation lesson has a bounded proposer/judge loop and baseline comparison, but its supplied benchmark, judge and guardrail cases are deterministic string fixtures. They are not live SWE-bench, model judging or production PII enforcement. The verification-gate lesson checks submitted command/exit records and scope reports; their contents still require a trusted collector. [Evaluation lesson](https://github.com/rohitg00/ai-engineering-from-scratch/blob/7a181b46332db6d2e1274c798e851bf978a008a9/phases/14-agent-engineering/30-eval-driven-agent-development/code/main.py), [verification lesson](https://github.com/rohitg00/ai-engineering-from-scratch/blob/7a181b46332db6d2e1274c798e851bf978a008a9/phases/14-agent-engineering/38-verification-gates/code/main.py).

**Best fit:** use the correction-to-control structure to improve SwarmMojo's existing inactive [skill drafts](../../app/trajectory_recorder.py) and workshop tests. Keep proposed changes reviewable; run accepted tests through the existing validator. Do not import the curriculum as a second runtime or describe its lesson output as demonstrated learning.

## OpenDots: strongest reference for a future business workspace

The concrete strengths are persisted review receipts keyed by conversation/tool call, rejection when a retry changes the approved draft, and page updates that compare the expected revision before writing. Permission checks run again when tools execute. These patterns suit invoice drafts, scheduling proposals and website copy. [Page storage and review receipts](https://github.com/CopilotKit/OpenDots/blob/625452e06cde74cb25b0ce319e2c1be0488f5a5f/src/server/pages.ts), [tool authorization](https://github.com/CopilotKit/OpenDots/blob/625452e06cde74cb25b0ce319e2c1be0488f5a5f/src/server/page-tools.ts), [review regression tests](https://github.com/CopilotKit/OpenDots/blob/625452e06cde74cb25b0ce319e2c1be0488f5a5f/tests/page-review.test.tsx).

The review card is an available flow, not a universal save barrier: direct create/edit tools also exist. Its agent prompt selects review when requested. Computer controls are checked server-side, but require a separate computer service. “Automatic Learning” selects a CopilotKit Intelligence learning container; it is not a local self-training algorithm supplied by this file. [Agent integration](https://github.com/CopilotKit/OpenDots/blob/625452e06cde74cb25b0ce319e2c1be0488f5a5f/src/server/dot-agent.ts), [computer service](https://github.com/CopilotKit/OpenDots/blob/625452e06cde74cb25b0ce319e2c1be0488f5a5f/src/server/computer-service.ts), [learning routing](https://github.com/CopilotKit/OpenDots/blob/625452e06cde74cb25b0ce319e2c1be0488f5a5f/src/server/learning.ts).

**Best fit:** borrow the approval/recovery interaction and storage contract for a thin SwarmMojo UI. Bind receipts to exact proposed content and source revision, and enforce required business approvals in the server. Preserve [harness preparation's](../../app/harness.py) no-execution response and existing workshop promotion authority. Adopting OpenDots wholesale would also adopt its Node/React application and connected-service architecture; that is a separate product decision, not necessary for portable local preparation.

## E2E candidate: useful proof and cleanup patterns

The candidate implements typed journeys with seed gates, steps, proof checks, artifacts and run-owned resource cleanup. Cleanup excludes resources absent from the ownership ledger; deletion failures are recorded and can prevent reseeding. This adds useful structure for future website and service-adapter tests. [Core implementation](https://github.com/aitoroses/agent-e2e-harness/blob/6bb9f145fcf97cdc4b9b7872da1bdc728b1b1a04/packages/harness/src/core/index.ts), [ownership tests](https://github.com/aitoroses/agent-e2e-harness/blob/6bb9f145fcf97cdc4b9b7872da1bdc728b1b1a04/packages/harness/test/ownership-ledger.test.ts).

A concrete adaptation requirement: unsupported resource kinds are recorded as skipped, while the verification runner calls cleanup passed when its failure list is empty. SwarmMojo must distinguish “all owned resources deleted” from “no deletion raised an error.” Resource ownership also has to come from the trusted test runner, not an agent-supplied list of arbitrary targets. [Cleanup runner](https://github.com/aitoroses/agent-e2e-harness/blob/6bb9f145fcf97cdc4b9b7872da1bdc728b1b1a04/packages/harness/src/verify/runner.ts).

**Conditional fit:** reuse the journey/artifact/ownership contract as an optional registered validator. It overlaps existing build and validation infrastructure; it is neither a memory engine nor permission to run arbitrary journey code. Confirm the intended “e2e” identity before choosing this dependency.

## Suggested measured improvement

Start with a **reviewable correction-to-regression queue**, backed by the existing lesson store and validator. Each item records source run/revision, observed failure, correction, proposed test or skill change, and approval status. Repeated retrieval can rank a candidate; it cannot activate it. Add receipt/revision patterns from OpenDots when a UI is built.

Acceptance before adoption:

1. Build a fixed set of representative tasks and held-out paraphrases for ten observed failure patterns. Record baseline verified success, repeat-failure rate, false-abstention rate, duration and context size. Keep failures and timeouts in the denominator.
2. Test candidate changes against the same fixtures and held-out cases. Require improvement on the targeted recurring failures, no new scope/approval violations and no decrease in the existing success suite. Report actual measurements; this review provides no claimed gain.
3. Exercise duplicate submissions, restart after remote success, changed drafts, stale revisions, revoked permission, interrupted validation, contradictory lessons and retraction. Require one intended effect per approved receipt and no activation without the recorded approval and validator result.
4. For browser/service tests, require API-observed outcomes and explicit cleanup completion. An unsupported cleanup adapter or leftover owned resource makes the run incomplete, never silently passed. No production invoice, calendar change, publication or message is part of this research.
