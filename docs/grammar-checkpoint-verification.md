# Formatted native checkpoints — 2026-10-06

The native adapter now exports and restores the fixed answer grammar together with the actual recurrent model state. This finishes the low-level formatted-state gap from the earlier [answer-format increment](native-answer-verification.md). `RWKV7Session.snapshot()` and `.restore()` expose opaque bounded byte buffers to Mojo callers.

Formatted state has a versioned 32-byte envelope, accepted token history, and the native runtime payload. Restore checks lengths, context/token bounds, format agreement and grammar replay using an independent sampler before changing the live context. A native import failure invalidates the session until a successful restore. Cancellation remains sticky. Plain state keeps its previous layout.

These are authenticated-caller APIs: the persistence layer must verify model/runtime/context identity and authenticate bytes before import. Grammar checks do not make the upstream native state parser a hostile-file parser. Existing persisted checkpoints bind the adapter hash and cannot silently migrate between builds.

## Verification

- Five real C/model tests passed, including partial formatted continuation, independent forks, completed/empty restores, format mismatch, malformed envelope/history rejection, failed native import recovery, sticky cancellation and unchanged state after buffer queries.
- Fourteen compiled Mojo binding tests passed, including plain and formatted save/restore with identical subsequent token bytes.
- The extended allocation-failure test passed: a failed grammar restore leaves the previous valid snapshot intact and a subsequent retry succeeds.
- After installation, eight native broker/worker tests and four existing workbench checkpoint tests passed together: **12 passed, zero skipped**, in 71.71 seconds. The broker tests include actual MCP-grounded 2.9B generation and worker cleanup.

Installed adapter SHA-256: `1ae120ece0e06f88f9d95a40eb3526b92cc6049e198094780cd5d8a2469b977e`. Source: `b8e8c798f0939a377f59979c3bc1c8d1382f5290de2254850a470f820e468fe4`. Header: `a5f3f0a1372802bd15559dc9b021fd250338a707091348e05e83dec1d0dd44fd`.

The previous adapter is retained in `deployment/backups/native-adapter-before-grammar-state`. The rebuilt worker has the same executable hash (`6e9c0f401c4acf7e066dfb1cb9c6fc8e6b47c7107f8c918f1306528459235824`); its updated manifest binds the new adapter and Mojo source. Unused snapshot methods do not change the worker's executable code. Its prior executable/manifest/drop-in are retained in `deployment/backups/native-worker-before-ed45fe941c144745b87b2702559fc986`.

Broker project chat still owns one ephemeral session per request. Durable formatted conversation storage, turn journals and broker save/restore/fork commands remain unfinished under T10. This change does not enable training, load 7.2B or certify the full custom OS.
