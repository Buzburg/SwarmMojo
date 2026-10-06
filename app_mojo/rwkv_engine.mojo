"""Move-only CPU model session using native/rwkv_state.h (Linux x86-64).

Link the verified adapter explicitly. The caller supplies a rendered prompt and
owns conversation policy, deadlines and persisted checkpoint authentication.
Token pieces are bytes: an individual piece need not be valid UTF-8.
"""
from std.ffi import c_int, c_uint, external_call


def check_native(result: c_int, operation: String) raises:
    if result != 0:
        raise Error(operation + " failed (native code " + String(Int(result)) + ")")


struct RWKV7Session(Movable):
    """Exclusive session ownership; close is idempotent and destruction releases it.

    Call operations serially. Do not share the raw handle or race close with calls.
    CPU cancellation is sticky until reset; an interrupted decode additionally
    requires verified native state restoration, which this binding does not expose.
    """
    var _handle: UInt

    def __init__(out self, path: String, context: Int = 4096, threads: Int = 4) raises:
        self._handle = 0
        if context < 128 or context > 32768 or threads < 1 or threads > 128:
            raise Error("Invalid native session context or thread count")
        if path == "" or len(path.as_bytes()) > 4096 or "\0" in path:
            raise Error("Invalid native model path")
        var model_path = path
        var model = external_call["wb_model_open", UInt](model_path.as_c_string_span(), c_int(0))
        if model == 0:
            check_native(external_call["wb_error_code", c_int](), "Model load")
            raise Error("Model load returned no handle")
        self._handle = external_call["wb_session_new", UInt](model, c_uint(context), c_int(threads))
        var result = external_call["wb_error_code", c_int]()
        # The C session retains its model, including after the model handle closes.
        external_call["wb_model_close", NoneType](model)
        if self._handle == 0:
            check_native(result, "Session creation")
            raise Error("Session creation returned no handle")

    def __deinit__(deinit self):
        if self._handle != 0:
            external_call["wb_session_close", NoneType](self._handle)

    def close(mut self):
        if self._handle != 0:
            external_call["wb_session_close", NoneType](self._handle)
            self._handle = 0

    def is_open(self) -> Bool:
        return self._handle != 0

    def require_open(self) raises:
        if self._handle == 0:
            raise Error("Native session is closed")

    def prefill(mut self, prompt: String) raises:
        self.require_open()
        var size = len(prompt.as_bytes())
        if size == 0 or size > 65536:
            raise Error("Prompt must contain 1 to 65536 UTF-8 bytes")
        var text = prompt
        check_native(external_call["wb_prefill", c_int](
            self._handle, text.as_c_string_span(), c_int(size)), "Prefill")

    def next_piece(mut self) raises -> Tuple[Bool, List[UInt8]]:
        """Return (end-of-generation, bytes); no string decoding or hidden token loop."""
        self.require_open()
        var output = List[UInt8](length=256, fill=0)
        var size = List[c_int](length=1, fill=0)
        var result = external_call["wb_next", c_int](self._handle,
            output.unsafe_ptr(), c_int(len(output)), size.unsafe_ptr())
        if result == -6:
            var needed = Int(size[0])
            if needed <= len(output) or needed > 65536:
                raise Error("Native token exceeds the output byte budget")
            for _ in range(needed - len(output)):
                output.append(0)
            result = external_call["wb_next", c_int](self._handle,
                output.unsafe_ptr(), c_int(len(output)), size.unsafe_ptr())
        if result == 1:
            return (True, List[UInt8]())
        check_native(result, "Token decode")
        if size[0] < 0 or Int(size[0]) > len(output):
            raise Error("Native token returned an invalid byte count")
        var piece = List[UInt8]()
        for i in range(Int(size[0])):
            piece.append(output[i])
        return (False, piece^)

    def cancel(mut self) raises:
        self.require_open()
        check_native(external_call["wb_session_cancel", c_int](self._handle), "Cancel")

    def reset_cancel(mut self) raises:
        self.require_open()
        check_native(external_call["wb_session_reset_cancel", c_int](self._handle), "Reset cancel")
