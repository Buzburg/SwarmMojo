# Gateway cancellation and runtime timer repair

Completed-body HTTP requests now monitor client disconnection while awaiting ordinary chat or a structured project draft. Disconnection cancels and settles the owned upstream task before returning; repeated parent cancellation cannot interrupt its resource cleanup. Streaming chat retains Starlette's disconnect handling and now records cancellation as a failed trajectory rather than leaving it unfinished. An upstream rejection also records failure. Successful completed-response decoding is unchanged.

The helper uses the ASGI [`http.disconnect` event](https://asgi.readthedocs.io/en/latest/specs/www.html#disconnect-receive-event) after the request body is consumed. Internal status 499 denotes an already disconnected caller; it is not a successful completion. Project draft cancellation does not apply or approve project changes.

## Native runtime defect and patch

Real TCP fixture tests passed, but the first two installed-model checks failed their five-second slot-release bound. The gateway recorded cancellation and closed its upstream socket; the native model retained the active slot while the test repeatedly queried status.

Inspection of the pinned runtime found that [`server_response::recv_with_timeout`](https://github.com/ggml-org/llama.cpp/blob/46847e61582097979f539595d893d83d8e1d1af1/tools/server/server-queue.cpp#L450) restarted its one-second relative wait whenever any result notified the shared condition variable. Unrelated slot-status results could therefore postpone the connection-closed check indefinitely. The checked-in `config/llama-cancellation.patch` replaces the resetting relative wait with one `steady_clock` deadline and `wait_until`. It does not alter sampling, model state, token limits or prompts.

The source base remains `46847e61582097979f539595d893d83d8e1d1af1`. `config/build-inputs.json` separately pins the patch and its exact target preimage/postimage hashes. The builder preserves the clean base checkout and builds from a dedicated detached worktree containing exactly that modification. Modified patch inputs, changed prepared sources, extra untracked files and symlinked build sources are refused. Ignored compiler output can be reused. Tests verify preservation of rejected user edits.

The rebuild also exposed an upstream default that downloads prebuilt browser assets and can fall back to a moving `latest` asset. The initial downloaded assets were retained outside the input path and never installed. Both UI build and prebuilt-asset fetching are now disabled; existing UI input directories block the builder. The final build reported zero embedded assets. The service remains accessible through its existing local APIs and Goose launchers.

## Installed artifact

The CPU runtime was rebuilt with GNU 16.2.1, installed at `/opt/goose-runtime`, and the model service restarted with its existing 2.9B model and inference flags. The old directory is preserved intact at `/opt/goose-runtime-before-cancellation-20261006`. The installed `bin/omarchy-runtime.json` records the base revision, patch digest, UI setting and artifact hashes. Inspection of the running model process confirmed its executable and all six mapped llama/ggml libraries use the installed directory; their bytes matched the recorded hashes.

Patch SHA-256: `f76b2593fd6b4c62c9386736e6e8d49868a1e56a77f6711379a6faa34c526c22`.

| Installed file under `/opt/goose-runtime/bin` | SHA-256 |
| --- | --- |
| `llama-server` | `a52af071603f7dd5a9be2851e0b2cb684f6a98a66a2e09f2534b733281fbd5b9` |
| `libllama-server-impl.so` | `c042bc7d69efca68d0da5a792e10bebda47af5629e2661999ce60f9d37042db7` |
| `libllama.so` | `e7d1fa73277733e35deb3e57d129809f92b60ec1231f34b96e532393b7f73f20` |

## Evidence and limits

Forty-five focused gateway/lifecycle/draft/release tests passed. A separate 37-test input/patch/lifecycle run passed. Real HTTP tests exercise the actual ASGI authentication middleware and actual TCP sockets for non-streaming chat, streaming chat and project drafting, including a successful next request after upstream closure. The installed-model cancellation test then passed with the patched runtime; it explicitly observes generated tokens before disconnecting and continues frequent slot queries during cancellation. The corresponding unpatched runtime failed twice under that traffic.

The final installed profile passed **9/9 required groups**, with no required live group skipped: 267 offline regressions; 24 native broker tests; live 2.9B/ROMS readiness; nine container lifecycle tests; 13 sandbox tests; 40 staging/promotion tests; 22 worker/recovery tests; the installed worker boundary; and 32 model-assisted workflow/prompt/cancellation tests. The final cancellation assertion requires actual slot release within five seconds, including time spent querying status. The model workflow still completed a fixture draft, validation, operator-approved apply and rollback.

This increment closes the gateway-to-runtime cancellation path. A subsequent [broker scheduling increment](broker-scheduling-verification.md) propagates native client disconnection through that path, adds bounded queues and keeps status responsive during generation. Explicit user-facing task cancellation controls, physical process termination, prompt-processing interruption latency under arbitrary hardware load, recurrent-state rollback and the full native C adapter remain separate work. No model training or 7.2B activation occurred.
