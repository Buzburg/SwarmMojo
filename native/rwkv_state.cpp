// Opaque, exception-contained C ABI over the pinned llama.cpp runtime.
#include "llama.h"
#include "ggml-backend.h"
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
thread_local std::string error;
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
    llama_token next = -1;
    ~Session() { if (ctx) llama_free(ctx); }
};
template <typename F> int checked(F action) noexcept {
    try { error.clear(); action(); return 0; }
    catch (const std::exception & e) { error = e.what(); }
    catch (...) { error = "Unknown native runtime failure"; }
    return -1;
}
void decode(Session & s, const std::vector<llama_token> & tokens) {
    if (tokens.empty() || s.position + tokens.size() > llama_n_ctx(s.ctx))
        throw std::runtime_error("Empty input or session context exhausted");
    for (size_t start = 0; start < tokens.size(); start += 128) {
        int count = static_cast<int>(std::min<size_t>(128, tokens.size() - start));
        auto batch = llama_batch_init(count, 0, 1);
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
        if (result != 0) { s.ready = false; throw std::runtime_error("Native decode failed"); }
        s.position += count;
    }
    s.ready = true;
    auto * vocab = llama_model_get_vocab(s.model->value);
    auto * logits = llama_get_logits_ith(s.ctx, -1);
    if (!logits) { s.ready = false; throw std::runtime_error("Missing next-token logits"); }
    s.next = static_cast<llama_token>(std::max_element(logits, logits + llama_vocab_n_tokens(vocab)) - logits);
}
}
extern "C" {
const char * wb_error() noexcept { return error.c_str(); }
void * wb_model_open(const char * path, int gpu_layers) noexcept {
    Owner * result = nullptr;
    checked([&] {
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
        if (!handle || context < 128 || context > 32768 || threads < 1 || threads > 128)
            throw std::runtime_error("Invalid session parameters");
        auto session = std::make_unique<Session>();
        session->model = *static_cast<Owner *>(handle);
        auto params = llama_context_default_params();
        params.n_ctx = context;
        params.n_seq_max = 1;
        params.n_batch = params.n_ubatch = 128;
        params.n_threads = params.n_threads_batch = threads;
        session->ctx = llama_init_from_model(session->model->value, params);
        if (!session->ctx) throw std::runtime_error("Cannot allocate recurrent context");
        result = session.release();
    });
    return result;
}
void wb_session_close(void * handle) noexcept { delete static_cast<Session *>(handle); }
int wb_prefill(void * handle, const char * text, int size) noexcept {
    return checked([&] {
        auto & s = *static_cast<Session *>(handle);
        if (size < 1 || size > 65536) throw std::runtime_error("Invalid prompt size");
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
        auto & s = *static_cast<Session *>(handle);
        if (!s.ready) throw std::runtime_error("Session has no valid next-token logits");
        auto * vocab = llama_model_get_vocab(s.model->value);
        auto token = s.next;
        *size = 0;
        if (llama_vocab_is_eog(vocab, token)) { ended = 1; return; }
        *size = llama_token_to_piece(vocab, token, output, capacity, 0, true);
        if (*size < 0) throw std::runtime_error("Token piece exceeds output buffer");
        decode(s, {token});
    });
    return result < 0 ? result : ended;
}
int64_t wb_state_size(void * handle) noexcept {
    int64_t size = -1;
    checked([&] { size = 12 + llama_state_get_size(static_cast<Session *>(handle)->ctx); });
    return size;
}
int wb_state_get(void * handle, uint8_t * data, size_t size) noexcept {
    return checked([&] {
        auto & s = *static_cast<Session *>(handle);
        if (size < 12) throw std::runtime_error("State buffer too short");
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
        auto & s = *static_cast<Session *>(handle);
        if (size < 12) throw std::runtime_error("Truncated state");
        int32_t position, next; uint32_t ready;
        std::memcpy(&position, data, 4); std::memcpy(&ready, data + 4, 4);
        std::memcpy(&next, data + 8, 4);
        if (position < 0 || static_cast<uint32_t>(position) > llama_n_ctx(s.ctx) || ready > 1 ||
                (ready && (next < 0 || next >= llama_vocab_n_tokens(llama_model_get_vocab(s.model->value)))))
            throw std::runtime_error("Invalid state metadata");
        if (llama_state_set_data(s.ctx, data + 12, size - 12) != size - 12)
            throw std::runtime_error("Incomplete state restore");
        s.position = position; s.ready = ready; s.next = next;
    });
}
}
