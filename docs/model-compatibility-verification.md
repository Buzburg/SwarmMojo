# Selected model compatibility — October 6, 2026

The supplied 2.9B Q4_K_M file passed actual CPU and Vulkan inference checks using runtime revision `46847e61582097979f539595d893d83d8e1d1af1` and the existing cancellation patch. The installed assistant continues using CPU. Vulkan was tested in a separate authenticated process and was not installed over the working service.

## Publisher identity

Both supplied files match the byte count and SHA-256 in immutable Git LFS pointers from their quantization publisher:

| File | Publisher revision | Matching SHA-256 |
| --- | --- | --- |
| 2.9B Q4_K_M | [`ab60c5e00f988bf6ebc54144770c0a395f1429bf`](https://huggingface.co/shoumenchougou/RWKV7-G1g-2.9B-GGUF/blob/ab60c5e00f988bf6ebc54144770c0a395f1429bf/rwkv7-g1g-2.9b-Q4_K_M.gguf) | `72f0fbb674ca21acf035b66023083055f6cede4942deb1f1b8475390752cfdf3` |
| 7.2B Q8_0 | [`ed8edcb5eecfad7902a53238044ffb0f239918cd`](https://huggingface.co/shoumenchougou/RWKV7-G1k-7.2B-GGUF/blob/ed8edcb5eecfad7902a53238044ffb0f239918cd/rwkv7-g1k-7.2b-Q8_0.gguf) | `cc93dce01fb8750627e4ba2a853de7803655b2fa65b74206587a5d9620bba14f` |

Pointers retrieved through the corresponding `/raw/<revision>/<filename>` URLs are retained under `config/provenance/`. The input manifest now records publisher repository/revision, pointer and immutable download URL. Sizes are 1,919,047,616 and 7,930,820,544 bytes. No weights were downloaded or replaced. This establishes identity with the publisher's quantized artifacts; it does not independently reproduce quantization or certify upstream training data. The CPU report's earlier `unverified` field predates this pointer check.

## Actual runtime checks

Eight fixtures round-trip exactly through tokenize/detokenize on both backends: empty text, English, surrounding whitespace/tabs, code escapes/newlines, multilingual/combining text, emoji, literal model markers and an embedded NUL. Literal input uses `add_special=false` and `parse_special=false`.

Both backends matched the configured template against a multi-turn fixture preserving code whitespace. One-token generation stopped at its token limit. A separate request stopped on the observed first token's text without emitting it. A fresh, uncached, deterministic arithmetic request completed with visible answer `56` on both, within the unchanged 256-token limit. CPU retained trailing newlines while Vulkan did not; byte-identical output is not claimed. This raw-runtime fixture does not resolve the earlier intermittent gateway reasoning-budget failure or establish broad answer quality.

The GPU log identifies RWKV-7, 2.95B parameters, 902 tensors and **33/33 layers offloaded to `Vulkan0`, Microsoft Direct3D12 (AMD Radeon RX 6800M)**. Reported allocations were 1566.29 MiB GPU model weights, 20.62 MiB recurrent state, 13.13 MiB GPU compute, 262.52 MiB CPU-mapped model data and small host buffers. These are allocation categories, not total driver/application memory. Observed CPU service cgroup current/peak usage was about 4.88 GB; these accounting categories are not directly comparable.

The runtime logged EOS/EOT metadata warnings. Pinned `src/llama-vocab.cpp` inserts missing declared EOS/EOT IDs into the end-of-generation set before logging them. The resulting set contained token 0 (`<s>`) and 261 (two newlines). Warnings remain in the log; no GGUF metadata or tokenizer IDs were rewritten. WSL's Mesa Dozen 26.2.4 reports a non-conformant testing implementation. Short inference success is not sustained reliability/performance certification, and no speed advantage is claimed.

## Build and evidence

`scripts/build_llama.py --backend vulkan` uses the reviewed patched source's separate `build-vulkan` directory; CPU remains the default. The candidate manifest records backend and artifact hashes. UI asset downloads remain disabled. Signed Arch build packages added: shaderc 2026.4-1, glslang 1:1.4.363.0-1, vulkan-headers 1:1.4.363.0-1 and spirv-headers 1:1.4.363.0-1. GCC 16.2.1 completed with upstream warnings visible in command output.

Candidate directory: `/home/rryan/.local/share/omarchy-harness/llama.cpp-patched-f76b2593fd6b/build-vulkan/bin`.

- Candidate `llama-server` SHA-256: `ee92eb536c14baec6b2a1bdb64e80539b6e2f55513e34a1840c2c52de2eb870a`.
- Candidate `libggml-vulkan.so` SHA-256: `e780f294ab7c6d6a5cadb08fbf5ff665f4f5de053c807adae2751d4abf071a3e`.
- [CPU result](../../deployment/model-compatibility-cpu.json).
- [Final Vulkan result and full artifact hashes](../../deployment/model-compatibility-vulkan-placement.json), [placement/load log](../../deployment/model-compatibility-vulkan-placement.log).
- [Initial GPU result](../../deployment/model-compatibility-vulkan.json): inference passed, but verification correctly failed because default verbosity omitted placement evidence. The final run enabled level 4 logging and passed without relaxing assertions.

The probe verifies model/runtime bytes, uses a separate loopback port and fresh API key, and terminates/reaps the candidate; final exit was clean. Installed model, ROMS and broker services remained active and reported ready afterward. Thirty model-input/patch regressions and two prompt-unit checks passed; the opt-in live prompt test was skipped in that unit run. The separate CPU/GPU checks above provide actual inference evidence.

This closes T08's selected 2.9B model-load gate. Native C adapter/state operations, long-context behavior, sustained benchmarks, broad quality and the full product remain unfinished. The 7.2B file was identified but not loaded; fine-tuning remains deferred to the new computer.
