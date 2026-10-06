#ifndef OMARCHY_RWKV_STATE_H
#define OMARCHY_RWKV_STATE_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
#define WB_NOEXCEPT noexcept
extern "C" {
#else
#define WB_NOEXCEPT
#endif

enum wb_result {
    WB_OK = 0, WB_END = 1, WB_RUNTIME_ERROR = -1, WB_INVALID_ARGUMENT = -2,
    WB_OUT_OF_MEMORY = -3, WB_CANCELLED = -4, WB_INVALID_STATE = -5,
    WB_BUFFER_TOO_SMALL = -6
};

/* Handles are opaque and owned. Close each at most once; stale/foreign handles
 * are invalid C pointers, not supported inputs. Null handles are rejected.
 * Sessions retain their model after model_close. Serialize close against every
 * operation; other session calls serialize internally. cancel may run concurrently.
 * All spans must reference live caller-owned storage for the supplied length.
 * Errors are thread-local; their text remains valid until this thread's next call.
 * Sampling is greedy. No stochastic/RNG or file-format compatibility is implied. */
const char * wb_error(void) WB_NOEXCEPT;
int wb_error_code(void) WB_NOEXCEPT;
void * wb_model_open(const char * path, int gpu_layers) WB_NOEXCEPT;
void wb_model_close(void * model) WB_NOEXCEPT;
void * wb_session_new(void * model, uint32_t context, int threads) WB_NOEXCEPT;
void wb_session_close(void * session) WB_NOEXCEPT;
int wb_session_cancel(void * session) WB_NOEXCEPT;
int wb_session_reset_cancel(void * session) WB_NOEXCEPT;
int wb_tokenize(void * model, const char * text, int bytes, int add_special,
                int parse_special, int32_t * tokens, int capacity, int * needed) WB_NOEXCEPT;
int wb_prefill(void * session, const char * text, int bytes) WB_NOEXCEPT;
/* BUFFER_TOO_SMALL reports the needed byte count without advancing the session.
 * END returns size=0. Output is raw UTF-8 token bytes, not NUL-terminated text. */
int wb_next(void * session, char * output, int capacity, int * size) WB_NOEXCEPT;
int64_t wb_state_size(void * session) WB_NOEXCEPT;
int wb_state_get(void * session, uint8_t * data, size_t size) WB_NOEXCEPT;
/* Import only integrity-checked state from the identical model/runtime/context.
 * A failed native decode/import invalidates the session until successful restore.
 * Caller validates compatibility and authenticates persisted bytes before import. */
int wb_state_set(void * session, const uint8_t * data, size_t size) WB_NOEXCEPT;

#ifdef __cplusplus
}
#endif
#undef WB_NOEXCEPT
#endif
