// Opaque, exception-contained C ABI over the pinned llama.cpp runtime.
#include "llama.h"
#include "rwkv_state.h"
#include "ggml-backend.h"
#include <algorithm>
#include <atomic>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
thread_local char error[256] = {};
thread_local int error_code = WB_OK;
struct Failure : std::runtime_error {
    int code;
    Failure(int code, const char * text) : std::runtime_error(text), code(code) {}
};
void require(bool condition, int code, const char * message) {
    if (!condition) throw Failure(code, message);
}
std::once_flag initialized;
struct Model {
    llama_model * value = nullptr;
    ~Model() { if (value) llama_model_free(value); }
};
using Owner = std::shared_ptr<Model>;
struct Session {
    Owner model;
    llama_context * ctx = nullptr;
    int32_t position = 0;
    bool ready = false;
    bool valid = true;
    std::atomic<bool> cancelled{false};
    std::mutex mutex;
    llama_token next = -1;
    ~Session() { if (ctx) llama_free(ctx); }
};
template <typename F> int checked(F action) noexcept {
    error[0] = 0; error_code = WB_OK;
    try { action(); return WB_OK; }
    catch (const Failure & e) { error_code = e.code; std::snprintf(error, sizeof(error), "%s", e.what()); }
    catch (const std::bad_alloc &) { error_code = WB_OUT_OF_MEMORY; std::snprintf(error, sizeof(error), "Allocation failed"); }
    catch (const std::exception & e) { error_code = WB_RUNTIME_ERROR; std::snprintf(error, sizeof(error), "%s", e.what()); }
    catch (...) { error_code = WB_RUNTIME_ERROR; std::snprintf(error, sizeof(error), "Unknown native runtime failure"); }
    return error_code;
}
Session & session(void * handle) {
    require(handle != nullptr, WB_INVALID_ARGUMENT, "Null session handle");
    return *static_cast<Session *>(handle);
}
void active(Session & s) {
    require(s.valid, WB_INVALID_STATE, "Session invalid; restore a verified checkpoint");
    require(!s.cancelled.load(), WB_CANCELLED, "Session cancelled");
}
void decode(Session & s, const std::vector<llama_token> & tokens) {
    active(s);
    if (tokens.empty() || s.position + tokens.size() > llama_n_ctx(s.ctx))
        throw std::runtime_error("Empty input or session context exhausted");
    for (size_t start = 0; start < tokens.size(); start += 128) {
        int count = static_cast<int>(std::min<size_t>(128, tokens.size() - start));
        auto batch = llama_batch_init(count, 0, 1);
        require(batch.token && batch.pos && batch.n_seq_id && batch.seq_id && batch.logits,
                WB_OUT_OF_MEMORY, "Batch allocation failed");
        batch.n_tokens = count;
        for (int i = 0; i < count; ++i) {
            batch.token[i] = tokens[start + i];
            batch.pos[i] = s.position + i;
            batch.n_seq_id[i] = 1;
            batch.seq_id[i][0] = 0;
            batch.logits[i] = (start + i + 1 == tokens.size());
        }
        int result = llama_decode(s.ctx, batch);
        llama_batch_free(batch);
        if (result != 0) {
            s.ready = false; s.valid = false;
            throw Failure(s.cancelled.load() ? WB_CANCELLED : WB_RUNTIME_ERROR, "Native decode failed or cancelled");
        }
        s.position += count;
    }
    s.ready = true;
    auto * vocab = llama_model_get_vocab(s.model->value);
    auto * logits = llama_get_logits_ith(s.ctx, -1);
    if (!logits) { s.ready = false; s.valid = false; throw std::runtime_error("Missing next-token logits"); }
    s.next = static_cast<llama_token>(std::max_element(logits, logits + llama_vocab_n_tokens(vocab)) - logits);
}
}
extern "C" {
const char * wb_error() noexcept { return error; }
int wb_error_code() noexcept { return error_code; }
void * wb_model_open(const char * path, int gpu_layers) noexcept {
    Owner * result = nullptr;
    checked([&] {
        require(path && strnlen(path, 4097) > 0 && strnlen(path, 4097) <= 4096 && gpu_layers >= 0 && gpu_layers <= 4096,
                WB_INVALID_ARGUMENT, "Invalid model path or GPU layer count");
        std::call_once(initialized, [] {
            llama_log_set([](ggml_log_level level, const char * text, void *) {
                if (level >= GGML_LOG_LEVEL_WARN) std::fputs(text, stderr);
            }, nullptr);
            ggml_backend_load_all(); llama_backend_init();
        });
        auto model = std::make_shared<Model>();
        auto params = llama_model_default_params();
        params.n_gpu_layers = gpu_layers;
        model->value = llama_model_load_from_file(path, params);
        if (!model->value) throw std::runtime_error("Cannot load the GGUF model");
        if (!llama_model_is_recurrent(model->value)) throw std::runtime_error("Expected an actual recurrent model");
        result = new Owner(model);
    });
    return result;
}
void wb_model_close(void * handle) noexcept { delete static_cast<Owner *>(handle); }
void * wb_session_new(void * handle, uint32_t context, int threads) noexcept {
    Session * result = nullptr;
    checked([&] {
        require(handle && context >= 128 && context <= 32768 && threads >= 1 && threads <= 128,
                WB_INVALID_ARGUMENT, "Invalid session parameters");
        auto session = std::make_unique<Session>();
        session->model = *static_cast<Owner *>(handle);
        auto params = llama_context_default_params();
        params.n_ctx = context;
        params.n_seq_max = 1;
        params.n_batch = params.n_ubatch = 128;
        params.n_threads = params.n_threads_batch = threads;
        params.abort_callback = [](void * data) { return static_cast<Session *>(data)->cancelled.load(); };
        params.abort_callback_data = session.get();
        session->ctx = llama_init_from_model(session->model->value, params);
        if (!session->ctx) throw std::runtime_error("Cannot allocate recurrent context");
        result = session.release();
    });
    return result;
}
void wb_session_close(void * handle) noexcept { delete static_cast<Session *>(handle); }
int wb_session_cancel(void * handle) noexcept {
    return checked([&] { session(handle).cancelled.store(true); });
}
int wb_session_reset_cancel(void * handle) noexcept {
    return checked([&] { auto & s = session(handle); std::lock_guard<std::mutex> lock(s.mutex); s.cancelled.store(false); });
}
int wb_tokenize(void * handle, const char * text, int bytes, int add_special, int parse_special,
                int32_t * tokens, int capacity, int * needed) noexcept {
    return checked([&] {
        require(handle && text && needed && bytes >= 0 && bytes <= 65536 && capacity >= 0 &&
                (capacity == 0 || tokens) && (add_special == 0 || add_special == 1) && (parse_special == 0 || parse_special == 1),
                WB_INVALID_ARGUMENT, "Invalid tokenization buffers or flags");
        auto * vocab = llama_model_get_vocab((*static_cast<Owner *>(handle))->value);
        int count = llama_tokenize(vocab, text, bytes, tokens, capacity, add_special, parse_special);
        *needed = count < 0 ? -count : count;
        require(count >= 0, WB_BUFFER_TOO_SMALL, "Token buffer too small");
    });
}
int wb_prefill(void * handle, const char * text, int size) noexcept {
    return checked([&] {
        auto & s = session(handle);
        std::lock_guard<std::mutex> lock(s.mutex);
        active(s);
        require(text && size >= 1 && size <= 65536, WB_INVALID_ARGUMENT, "Invalid prompt span");
        auto * vocab = llama_model_get_vocab(s.model->value);
        int count = llama_tokenize(vocab, text, size, nullptr, 0, s.position == 0, true);
        if (count >= 0) throw std::runtime_error("Cannot size prompt tokens");
        std::vector<llama_token> tokens(-count);
        count = llama_tokenize(vocab, text, size, tokens.data(), tokens.size(), s.position == 0, true);
        if (count <= 0) throw std::runtime_error("Cannot tokenize prompt");
        tokens.resize(count);
        decode(s, tokens);
    });
}
int wb_next(void * handle, char * output, int capacity, int * size) noexcept {
    int ended = 0;
    int result = checked([&] {
        auto & s = session(handle);
        std::lock_guard<std::mutex> lock(s.mutex);
        active(s);
        require(size && capacity >= 0 && (capacity == 0 || output), WB_INVALID_ARGUMENT, "Invalid output span");
        require(s.ready, WB_INVALID_STATE, "Session has no valid next-token logits");
        auto * vocab = llama_model_get_vocab(s.model->value);
        auto token = s.next;
        *size = 0;
        if (llama_vocab_is_eog(vocab, token)) { ended = 1; return; }
        *size = llama_token_to_piece(vocab, token, output, capacity, 0, true);
        if (*size < 0) { *size = -*size; throw Failure(WB_BUFFER_TOO_SMALL, "Token piece exceeds output buffer"); }
        decode(s, {token});
    });
    return result < 0 ? result : ended;
}
int64_t wb_state_size(void * handle) noexcept {
    int64_t size = -1;
    checked([&] {
        auto & s = session(handle); std::lock_guard<std::mutex> lock(s.mutex);
        active(s); size = 12 + llama_state_get_size(s.ctx);
    });
    return size;
}
int wb_state_get(void * handle, uint8_t * data, size_t size) noexcept {
    return checked([&] {
        auto & s = session(handle); std::lock_guard<std::mutex> lock(s.mutex);
        active(s);
        require(data && size == 12 + llama_state_get_size(s.ctx), WB_INVALID_ARGUMENT, "State export span must match exact size");
        std::memcpy(data, &s.position, 4);
        uint32_t ready = s.ready ? 1 : 0;
        std::memcpy(data + 4, &ready, 4);
        std::memcpy(data + 8, &s.next, 4);
        if (llama_state_get_data(s.ctx, data + 12, size - 12) != size - 12)
            throw std::runtime_error("Incomplete state export");
    });
}
int wb_state_set(void * handle, const uint8_t * data, size_t size) noexcept {
    return checked([&] {
        auto & s = session(handle); std::lock_guard<std::mutex> lock(s.mutex);
        require(data && size >= 12 && size <= 512 * 1024 * 1024, WB_INVALID_ARGUMENT, "Invalid state span");
        int32_t position, next; uint32_t ready;
        std::memcpy(&position, data, 4); std::memcpy(&ready, data + 4, 4);
        std::memcpy(&next, data + 8, 4);
        if (position < 0 || static_cast<uint32_t>(position) > llama_n_ctx(s.ctx) || ready > 1 ||
                (ready && (next < 0 || next >= llama_vocab_n_tokens(llama_model_get_vocab(s.model->value)))))
            throw std::runtime_error("Invalid state metadata");
        s.valid = false; s.ready = false;
        if (llama_state_set_data(s.ctx, data + 12, size - 12) != size - 12)
            throw std::runtime_error("Incomplete state restore");
        s.position = position; s.ready = ready; s.next = next; s.valid = true;
    });
}
}
