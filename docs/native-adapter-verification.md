# Opaque native model ABI

The existing `native/rwkv_state.cpp` adapter now has a public C header, checked null/span arguments, stable integer errors, thread-local bounded error text and native CPU cancellation. Its existing `wb_*` entry points remain compatible with the workshop Python wrapper. This increment hardens that adapter; the installed broker still uses its authenticated HTTP generation path.

`native/rwkv_state.h` defines ownership and lifetime requirements. Sessions retain the model after the caller releases its model handle. Each handle must be closed once; close must be serialized against its operations. Session mutations serialize internally, while the atomic cancellation request may run concurrently. Null operational handles fail safely; closing a null handle is a no-op. Stale/foreign pointers and spans that do not reference accessible caller storage remain invalid C usage.

Tokenization exposes explicit special-token flags and caller-owned output storage. A too-small token or generation buffer reports its required size without advancing the session. State export requires the exact reported length. C++ exceptions stay inside the boundary; allocation failure returns `WB_OUT_OF_MEMORY`. Error text uses fixed thread-local storage, avoiding another allocation in the failure handler.

Decode uses fixed owned batch buffers instead of the upstream batch helper's unchecked allocations. Before native mutation it invalidates old logits; failure or cancellation leaves the session invalid until a successful restore. Failed native state import also invalidates the session. Callers must authenticate saved bytes and check model/runtime/context compatibility before native import; this low-level API is not a hostile-file parser. The existing workshop validates checkpoint metadata and replaces its context separately.

Sampling remains greedy, with no stochastic sampler/RNG state. Native cancellation was verified on CPU through the runtime abort callback. GPU abort behavior, arbitrary forged state buffers, OS out-of-memory termination and a full broker conversation/state journal are not certified here.

## Actual verification

The header compiled as C11 with warnings treated as errors. Three native test cases use the actual shared library and 2.9B model, with crash-prone checks isolated in a subprocess:

- Null/invalid arguments and a missing model return errors without crashing.
- Model ownership survives caller-handle closure; too-small output preserves state; saved continuation matches after restore and across independently mutable sessions. Truncated native import invalidates the affected session, and valid restore recovers it.
- Twelve create/cancel/destroy cycles remain below the test's 64 MiB resident-growth threshold. In-flight CPU decode cancellation settles within ten seconds, invalidates its session and permits recovery from a verified snapshot.
- A separately compiled C++ allocation-failure fixture forces `std::bad_alloc` during model/session creation. Both return the documented error and succeed on a subsequent retry. This is deterministic boundary fault injection, not physical memory exhaustion.

The existing four-test workshop checkpoint suite also passed against this adapter, including the actual model continuation/fork path. `verify_all.py --offline --native-adapter` requires explicit existing `OMARCHY_NATIVE_ADAPTER` and `OMARCHY_STATE_MODEL` artifacts; missing inputs fail rather than allowing skipped tests to certify the ABI.

The final installed-artifact profile passed **3/3 groups**: 273 offline regressions, 46 compiled broker/MCP tests plus 13 subtests, and all three actual native-adapter tests. No required group in that run was skipped.

## Installed workshop artifact

The adapter was built against the pinned public runtime headers and verified installed library hashes. The builder also rejects modified public include trees and mismatched runtime patch identity, and records the new public header hash. Rebuilding with these checks reproduced the installed library bytes.

Installed workshop library: `build/libomarchy_state.so`, SHA-256 `123f510d4bbcf85262a0ab378f1fe1393c10b194ff7cf9200c75d6eb440a08e2`. Its adjacent manifest records source/header/runtime hashes. The prior library and manifest are preserved in `deployment/backups/native-adapter-before-abi-hardening` in the parent workspace. Replacement used new files and atomic rename, preserving existing mappings rather than truncating a loaded library.

The model service and native broker binary were not replaced. Mojo-to-C wiring, memory-grounded native conversation, runtime-derived backend/session status, sequenced streaming and durable turn recovery remain open under T09/T10. No 7.2B loading or training occurred.
