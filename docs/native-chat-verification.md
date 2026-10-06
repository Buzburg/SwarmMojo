# Direct Mojo model conversations

Project-scoped broker chat now calls the compiled Mojo model worker after its real ROMS MCP lookup. The worker uses `RWKV7Session` and the verified C adapter directly; generation does not call the HTTP model server. Plain chat retains the existing HTTP path. Empty project context still returns an explicitly non-generated notice.

The first native implementation owns one process/session per request. Model loading and full model-file hashing happen in that process so they cannot block broker status or socket cancellation. Each request verifies the supplied 2.9B model, adapter, linked runtime libraries, worker binary and relevant source identities. The shared verifier was extracted from the existing checkpoint wrapper without changing its identity fields. A missing or changed input fails; there is no silent HTTP fallback after selecting native generation.

The broker renders the existing pinned User/Assistant template with the prepared context and current-time instructions. Input is capped at 16 KiB of UTF-8 rendered prompt and a 64 KiB worker request; generation uses the fixed JSON-answer grammar, greedy CPU sampling, a 4096-token session, four threads and at most 512 generated tokens. Both worker output streams have byte limits. The native action has a 110-second deadline plus bounded cleanup, within the broker's existing queue and action lifecycle. Oversized tokenized context can still fail; byte bounds are not an exact tokenizer budget.

The worker's environment contains only the selected interpreter/library paths, basic process settings and model path. Gateway/model/API secrets are excluded. Model input travels over stdin rather than process arguments. The compiled worker establishes Linux parent-death `SIGKILL` and checks the expected parent before importing Python or loading the model.

Cancellation owns process creation even if it arrives during spawn. Cleanup drains pipes, first requests termination, then uses forced termination if necessary, and waits for process exit before releasing the action. Repeated cancellation cannot interrupt cleanup. An unconfirmed cleanup leaves visible retained state and prevents further native generation. The parent-death check verifies no running worker survives its owner's forced death; an exited adopted process may briefly remain a zombie until the system reaps it.

## Runtime facts

The worker emits a bounded ready event only after verified model/session creation and grammar setup. Broker status reports active processes, loaded sessions, verified model/adapter/runtime identities and the configured CPU session parameters from that event. It distinguishes a process still loading from a confirmed loaded session by its counts. Once the worker exits, loaded sessions return to zero; idle status does not claim a model remains resident. Successful project replies include the runtime facts and actual generated-token count. Counts do not certify retained conversation state.

## Actual verification

The final `verify_all.py --offline --native-chat` run against the installed worker passed **3/3 required groups** with no required skips: 274 offline regressions, 67 compiled broker/MCP tests plus 13 subtests, and eight native worker checks.

The native tests include an actual random-code lesson retrieved through MCP, answered by the supplied 2.9B model through the compiled broker while its HTTP gateway endpoint is unavailable. Source receipt and answer value are checked and the fixture database remains unchanged. Other real-process tests cover output overflow, deadline, repeated cancellation, a worker ignoring graceful termination, responsive broker status while the model is loaded, disconnection/reaping and parent death. The shared identity-check refactor also passed all four existing checkpoint tests, including actual recurrent continuation and independent forks.

Installed executable: `/opt/roms-env/bin/omarchy-model-worker`, SHA-256 `6e9c0f401c4acf7e066dfb1cb9c6fc8e6b47c7107f8c918f1306528459235824`. Its adjacent manifest binds the sources and adapter `04da483a66ebdcb3a93427132589ab6881b0c5ff75b7d60ab455ad026d8cca04`. `build_native_model_worker.py` builds into an explicit output; `install_native_chat.py` only installs already-built verified inputs and adds the broker service drop-in. Existing artifacts are preserved before replacement. This was the first worker installation, so no prior worker required backup. The HTTP model and gateway binaries were not replaced.

## Remaining work

Native project chat is currently one turn at a time. It does not preserve a resident session, serialize grammar state, journal turns, stream ordered events or expose broker save/restore/fork actions. Per-request full identity verification and model loading add latency. The normal Goose chat client still uses the HTTP conversation path; the new path is available through project-scoped broker requests. Persona versioning, complete memory integration, saved sessions, the full desktop and broader build gates remain unfinished. No model training or 7.2B loading occurred.
