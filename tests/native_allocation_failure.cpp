// Deterministic C++ allocation failure at the real adapter boundary.
#include "rwkv_state.h"
#include <cstdlib>
#include <new>

static bool fail_allocation = false;
void * operator new(std::size_t size) {
    if (fail_allocation) throw std::bad_alloc();
    if (auto * pointer = std::malloc(size ? size : 1)) return pointer;
    throw std::bad_alloc();
}
void operator delete(void * pointer) noexcept { std::free(pointer); }
void operator delete(void * pointer, std::size_t) noexcept { std::free(pointer); }

int main(int argc, char ** argv) {
    if (argc != 2) return 2;
    fail_allocation = true;
    auto model = wb_model_open(argv[1], 0);
    fail_allocation = false;
    if (model || wb_error_code() != WB_OUT_OF_MEMORY) return 3;
    model = wb_model_open(argv[1], 0);
    if (!model) return 4;
    fail_allocation = true;
    auto session = wb_session_new(model, 128, 1);
    fail_allocation = false;
    if (session || wb_error_code() != WB_OUT_OF_MEMORY) return 5;
    session = wb_session_new(model, 128, 1);
    if (!session) return 6;
    wb_session_close(session);
    wb_model_close(model);
    return 0;
}
