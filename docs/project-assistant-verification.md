# Model-assisted project workshop — October 5, 2026

Open `Open Project Workshop.cmd`, run `goose --project-workshop`, or type `/project` in Goose chat. Select an existing local Git repository, one to four relative file paths, available Python checks, and a plain-language change request. The workshop drafts in an isolated stage, runs the selected checks, displays the exact diff, and requires the displayed `APPLY` confirmation before touching source files. After applying, `UNDO` opens a separately confirmed rollback review. Leaving a review unconfirmed retains the draft for inspection.

This increment uses the installed Goose 2.9B model. Selected UTF-8 file contents may total 4096 bytes; the request may use 1024 bytes. The adapter measures the actual formatted input against a 3072-token budget and limits generation to 768 tokens within the configured 4096-token window. Incomplete output is rejected. The test-build checks are registered Python syntax and standard-library unittest checks; arbitrary shell commands, dependency installation and model-selected images are unavailable.

## Trust boundary

The gateway requires configured authentication and accepts only the bounded instruction/files contract. Project input is sent exclusively to its configured loopback native runtime. Structured generation uses the pinned runtime's `/apply-template`, `/tokenize` and `/completion` APIs with a JSON schema. These APIs are documented in the [pinned upstream server reference](https://github.com/ggml-org/llama.cpp/blob/46847e61582097979f539595d893d83d8e1d1af1/tools/server/README.md). Ordinary chat uses the shared prompt template and the separately documented [answer-format decoder](goose-response-verification.md); structured project output remains bound to its own strict JSON contract.

The model can propose replacement text or deletion only for the operator-selected paths. It cannot choose the project, base commit, preimage hashes, validation commands, approval or apply operation. The controller rejects extra fields, duplicate JSON keys, duplicate/unselected paths, incomplete responses and no-op proposals. Source revision and selected bytes are checked again after generation to protect edits made while waiting. Existing final newline conventions are preserved before computing the patch digest, without collapsing intentional blank lines; the raw model response and this formatting policy are recorded.

The workshop sends staged validation to the private rootless worker service. A passing check enables review, not automatic approval. Apply and rollback retain the existing exact-digest authorization, conflict detection and recovery journal. Displayed file/diff text is escaped to prevent terminal control sequences from acting as interface commands. A model reply containing `/project` is never treated as a user command.

Draft records and raw responses live under the private `ROMS_DATA_DIR/patches/drafts` directory. Task records, staged files and validation evidence use the existing patch store. Failed generation records its failure and does not modify the source checkout. Existing source-library indexing remains separate from project editing and model training.

## Verification

The focused tests cover constrained output, source edits during generation, duplicate keys, final-newline preservation, gateway authentication, disabled authentication configuration, invalid input, token overflow, incomplete generation and refusal of external inference backends. Interactive operator acceptance and refusal are exercised with an actual validation service and disposable source repositories.

The real-model fixture requests the exact change `VALUE = 1` to `VALUE = 2`, verifies the resulting bytes, runs the actual sandboxed syntax check, applies the reviewed patch and rolls it back. It checks the returned `goose-2.9b` identity and positive generated-token usage. This live fixture authorizes only its disposable repository. No user project is edited by verification. Ordinary installed chat also returned `56` for seven times eight after the structured-drafting integration.

The full profile passed **9/9 required groups**: 142 offline regression tests, 22 compiled native-broker tests, live model/ROMS readiness, nine rootless-worker tests, 13 native/combined sandbox tests, 40 staged-patch/promotion tests, 22 service/recovery tests, the installed service-boundary check, and 28 model-assisted workflow tests. The final group includes the real model roundtrip and both operator acceptance/refusal cases. No tests were skipped in this run.

The profile command is `scripts/verify_all.py --containers --sandbox --staging --drafts`; it requires explicit live-model enablement and the pinned native/container artifacts, so missing prerequisites cannot silently certify skipped live tests. The installed ordinary chat smoke check also passed after restoring its original chat parser. These results cover the tested workflow, not every remaining item in the PDF roadmap.

## Limits

This is a bounded operator-guided workflow for small changes, not broad coding-quality certification. Syntax checks do not prove semantic correctness. A model may propose an incorrect change even when checks pass; the concrete diff remains the operator's decision. Large projects, additional validation languages, asynchronous conversational tasks, desktop control, recurrent-state persistence, guest delegation and training remain separate work. The 7.2B upgrade is deferred to the new computer.
