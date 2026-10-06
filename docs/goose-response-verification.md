# Goose answer formatting — October 5, 2026

The extra broker smoke check had returned an empty reasoning block or an `<answer>` wrapper around the correct `URGENT` word. The final change keeps the previously working rendered prompt for ordinary messages and uses explicit response decoding. It does not alter the expected answer or remove assertions from the cutover check.

## Response contract

The installed native runtime uses automatic reasoning detection and its `deepseek` response format. The template can represent explicit `reasoning_content` in assistant history, allowing native reasoning fields to remain separate. For messages without that field, the rendered system/user/assistant text and final `Assistant:` prefix match the previous template. The measured installed template SHA-256 is `19e01f55a50c729b52e8d0e9bfc4c23c5e8845be1babb44465e815fa59af8a5f`.

For completed non-streaming responses whose model is exactly `goose-2.9b`, the ROMS decoder recognizes up to four complete leading `think`/`thinking` blocks and one complete outer `answer` wrapper. It moves substantive thought text into `reasoning_content`, preserves any native reasoning, and exposes the enclosed answer as `message.content`. Original content is returned under `roms_response_format.originals`, with a versioned decoder record. Token usage and finish status are unchanged.

The decoder operates only on bounded content of at most 16384 characters and requires a nonempty remaining answer. It preserves incomplete generations, open/nested/ambiguous wrappers, reasoning-only output, fenced examples, ordinary inline markup and other model aliases. Whole bare `answer` envelopes are interpreted as model framing; literal examples should be fenced, and original bytes remain inspectable in the response record. It neither checks factual correctness nor repairs a wrong answer.

Streaming responses still use native passthrough and are not normalized by this non-streaming decoder. The installed Goose terminal client and broker chat use non-streaming replies. Streaming parity remains part of later conversational integration.

## Evidence and decision

The [model author's template guide](https://github.com/BlinkDL/RWKV-LM/blob/main/RWKV-v7/RWKV7-G1x-templates.txt) documents the role/reasoning markers. The [pinned runtime reference](https://github.com/ggml-org/llama.cpp/blob/46847e61582097979f539595d893d83d8e1d1af1/tools/server/README.md) documents automatic reasoning and separate reasoning-content output. Suggested forced reasoning prefixes and alternate sampling settings produced loops or inconsistent formatting in this local checkpoint, so those experiments were not retained. No sampling-default or prompt-cache change was installed.

The actual installed gateway passed the arithmetic fixture with the exact visible answer `56` and a completed response. `scripts/check_wsl_build.py` then passed its unchanged exact-word local-policy assertion with `URGENT`, through the native broker, ROMS and real model. Authentication and private socket checks passed in that run. No tags are stripped by the assertions.

The decoder tests cover recognized complete envelopes, original-output retention, existing native reasoning, ambiguous/nested input, code/inline examples, other models and truncated generations. Template tests compare real native rendering with the local template and preserve whitespace in selected code. The live test now waits for installed services before requesting generation; its earlier immediate request during gateway restart failed on connection availability and is not counted as a model-answer pass.

The final combined run passed **73 tests** across answer decoding, actual native prompt rendering/chat, model-assisted drafting, the real validation/apply/rollback fixture, gateway boundaries and release regressions. The restarted gateway loaded the final decoder, including its nested-wrapper refusal. Broad answer quality, repetition behavior across tasks, streaming formatting and the remaining T08/T11 requirements are not certified by these small fixtures.
