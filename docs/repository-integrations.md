# Repository integrations for the future Omarchy machine

The customized ROMS branch remains the foundation. These tools extend the operator's build and project workshop; they do not add shell execution, approval, or installation permissions to the broker or model. Machine-local paths live in ignored `config/workbench.local.json`.

## Available tools

Run from the ROMS folder using its Linux Python environment:

```sh
python -m scripts.workbench status
python -m scripts.workbench configure --ptrm /path/to/ptrm-mojo --triad /path/to/triad-engine
python -m scripts.workbench build workbench.workflow.json
python -m scripts.workbench find /path/to/project function_name
python -m scripts.workbench log /path/to/original.log --max-lines 60 --max-bytes 6000
python -m scripts.workbench review task_ID
python -m scripts.workbench analyze runs.csv policy.json /path/to/new/report
python -m scripts.workbench verify-receipt RECEIPT_ID
```

WorkflowProof executes explicitly selected, operator-owned manifests with independent verification and fingerprints. It is a trusted host build tool, not a sandbox for model-generated commands. The supplied workflow runs portable integration checks and creates a verified source archive under `build/`. It does not certify native inference or target hardware. Custom manifests can reuse unchanged verified work; the supplied release checks deliberately rerun.

PTRM uses the reviewed external source checkout and its compiled `bin/ptrm-review-worker`. Triad uses its own pinned runtime and `scripts/run.sh`. Their paths can also be set with `OMARCHY_PTRM_ROOT` and `OMARCHY_TRIAD_ROOT`. Both fail visibly if unavailable; neither result authorizes a patch. Rebuild/reinstall these dependencies on the future Linux machine instead of copying relocated environments. The installed workshop supports `/find NAME` and displays PTRM findings after registered validation, before the existing exact-patch confirmation.

Symdex's language patterns are reused with fresh bounded file reads. Python definitions/calls use the AST to avoid comment/string matches; other languages remain heuristic. Queries never expand editable file selection. Symlinks, excluded credential paths, excessive files, binary content, and oversized files are rejected or explicitly omitted. Sieve's scoring is reused with enforced line and UTF-8 byte budgets. Original logs remain separate and unmodified; summaries carry the original text digest and a truncation flag.

## Authenticated evidence

TraceSeal receipts and its key reside in a private mode-0700 Linux directory, normally `~/.local/state/omarchy-workbench`. This directory must remain outside every worker stage and container mount. Recorded events are sealed by the operator process after it receives the result. Interrupted collection lacks a finalized checkpoint and cannot verify. The HMAC detects later changes against the selected checkpoint; it does not establish truth of submitted events or resist compromise of the same host account. Raw runtime logs stay private and are referenced by digest.

## Real recurrent checkpoints

```sh
python -m scripts.build_state_adapter
python -m scripts.verify_workbench --native --model /path/to/rwkv7-g1g-2.9b-Q4_K_M.gguf
python -m scripts.workbench state-run --library build/libomarchy_state.so \
  --model /path/to/rwkv7-g1g-2.9b-Q4_K_M.gguf --model-key 2.9b \
  --save conversation-1 'Reply briefly: what is 2 + 2?'
python -m scripts.workbench state-run --library build/libomarchy_state.so \
  --model /path/to/rwkv7-g1g-2.9b-Q4_K_M.gguf --model-key 2.9b \
  --restore conversation-1 --save branch-2 'Continue the explanation.'
```

The C adapter shares loaded model weights between independently allocated recurrent contexts. It uses the pinned backend's actual serialized memory, with the cached next greedy token because the backend's state export does not preserve next-token logits. Python owns versioned, authenticated storage, model/runtime/adapter/template/persona compatibility, the turn transcript, and atomic publication. Restores first populate a new context; invalid checkpoints cannot replace a valid active session. Interrupted directory writes leave the preceding checkpoint intact.

Chat renders the project's RWKV Jinja template with its existing double-newline turn delimiter. It captures the template bytes when creating a session and refuses a fork if the template has changed. The pinned Linux environment already includes Jinja; alternate environments must install `requirements-workbench.txt`. The default checkpoint store permits 2 GiB total serialized state, including interrupted saves, with a 512 MiB limit per state. It refuses new saves when full and never evicts previous checkpoints automatically. Saved turns include their stop/length finish reason.

Sampling is explicitly greedy with no RNG state; stochastic sampling and vector fusion are unsupported. The operator API is separate from the installed model service, so its checkpoints do not purport to snapshot that service's active chat. `state-run` creates a durable pending intent before generation and commits transcript plus state together. A pending intent after interruption must be inspected; it is never automatically retried. Checkpoint names are immutable. This provides an executable, tested foundation for future broker state routing without changing the current public protocol.

## Target qualification and alternate inference

```sh
python -m scripts.workbench baseline --model /path/to/model.gguf --model-key 2.9b
python -m scripts.workbench baseline --model /path/to/7.2b.gguf --model-key 7.2b-q8 --gpu-layers -1
python -m scripts.workbench probe --url http://127.0.0.1:8000 --model mojond --checkpoint-sha256 MODEL_SHA256
python -m scripts.workbench compare baseline.json candidate.json
```

Baseline starts and stops a separate hash-verified llama-server, measures process startup (filesystem cache may be warm), process peak RSS, repeated exact-answer fixtures, streaming disconnect, observed slot release, and next-request recovery. It records CPU/kernel/RAM and any model-layer offload reported by the runtime. No installed service is restarted. CPU measurements on this machine do not qualify the planned Ryzen AI Max+ 395 / 128 GB native desktop.

The generic endpoint probe cannot infer real checkpoint support or representative coding quality from HTTP success. Those remain missing until independently measured. The comparison gate requires matching machine, workload and model-checkpoint identities, at least ten representative tasks for each runtime, no task-success regression, lower median latency, and passing streaming/cancellation/recovery/recurrent-checkpoint evidence. Input reports are operator-supplied evidence; the gate never swaps services automatically. Mojond remains experimental because its current HTTP implementation lacks streaming and long-generation disconnect detection. Native desktop reboot/recovery, actual target GPU placement, 7.2B qualification, and comparative coding benchmarks must run on the future machine.

## Verified on the current WSL machine

The integration suite contains 22 tests, including one actual 2.9B-model checkpoint/restore/fork test. Portable builds expect that one native test to be skipped; native verification requires all 22 to pass. Existing validation also passed 55 live workshop/model tests, 273 offline Python regressions, and 46 native broker tests with 13 subtests. The real PTRM worker and Triad example analysis both executed successfully. Reports are under the harness's `review-artifacts/omarchy-repository-integration/` directory.

The isolated current-runtime baseline answered all six small exact-answer fixtures and passed streaming, disconnect cancellation and next-request recovery. A warm-cache process start took 3.06 seconds; observed peak RSS was about 3.33 GiB. These are observations on the current Ryzen 9 5980HX/WSL host, not target-machine or coding-performance claims. Mojond answered the same six fixtures but did not satisfy streaming, cancellation, recovery or recurrent-checkpoint gates, so the selected runtime remains unchanged.

The source archive is an integration overlay for this customized ROMS revision, not a standalone OS image. Inspect changes before overlaying another checkout, preserve that checkout's local edits, rebuild native binaries there, and configure local dependency paths. It contains no model weights, databases, runtime environments, receipt keys, or private machine configuration.

## Attribution

Pinned copies of Buzburg WorkflowProof, TraceSeal, Symdex and Sieve are under `app/workbench/vendor/`, with source hashes and original license/notice files. The integration hardens the Symdex/Sieve adapters without editing the copied originals. PTRM and Triad remain explicit external dependencies. Goose State supplied the checkpoint/branch use case; its synthetic float-vector files are not imported as model state. RetryFence/StateFresh recovery principles remain covered by the existing replay, stale-source and promotion tests instead of adding a second mutation controller.
