"""RWKV-7 recurrent state lifecycle, C FFI engine bindings, and temporal grounding in Mojo."""
from std.ffi import c_int, c_uint, c_long, external_call
from std.os import stat
from std.memory import Pointer

comptime SYS_READ = 0
comptime SYS_WRITE = 1
comptime O_RDONLY = 0
comptime O_WRONLY = 1
comptime O_CREAT = 64
comptime O_TRUNC = 512
comptime DEFAULT_MODE = 0o644


struct RWKVStateBuffer:
    """Contiguous in-memory recurrent state buffer for RWKV-7 linear recurrence."""
    var size: Int
    var data: List[Float32]

    def __init__(out self, size: Int):
        self.size = size
        self.data = List[Float32]()
        for _ in range(size):
            self.data.append(0.0)

    def element_count(self) -> Int:
        return self.size

    def byte_size(self) -> Int:
        return self.size * 4 # 4 bytes per Float32

    def save_to_disk(self, file_path: String) raises:
        """
        Atomic serialization of the recurrent state matrix to disk.
        Writes to a temporary sibling file and renames atomically to prevent corruption.
        """
        var tmp_path = file_path + ".tmp"
        var tmp_mut = tmp_path
        var target_mut = file_path

        var fd = external_call["open", c_int, num_fixed_args=3](
            tmp_mut.as_c_string_span(),
            c_int(O_WRONLY | O_CREAT | O_TRUNC),
            c_uint(DEFAULT_MODE)
        )
        if fd < 0:
            raise Error("Cannot open temporary state file for write: " + tmp_path)

        var bytes_to_write = self.byte_size()
        var raw_ptr = self.data.unsafe_ptr().unsafe_bitcast[UInt8]()
        var written = external_call["syscall", c_long](
            c_long(SYS_WRITE),
            c_int(fd),
            raw_ptr,
            UInt(bytes_to_write)
        )
        _ = external_call["close", c_int](fd)

        if written != c_long(bytes_to_write):
            _ = external_call["unlink", c_int](tmp_mut.as_c_string_span())
            raise Error("Failed to write complete state buffer to disk")

        var ren = external_call["rename", c_int](
            tmp_mut.as_c_string_span(),
            target_mut.as_c_string_span()
        )
        if ren != 0:
            raise Error("Failed to atomically rename state file to: " + file_path)

    def load_from_disk(mut self, file_path: String) raises -> Bool:
        """
        Sub-2ms cold restore of recurrent state directly into memory buffer.
        """
        var path_mut = file_path
        var fd = external_call["open", c_int, num_fixed_args=3](
            path_mut.as_c_string_span(),
            c_int(O_RDONLY),
            c_uint(0)
        )
        if fd < 0:
            return False

        var bytes_to_read = self.byte_size()
        var raw_ptr = self.data.unsafe_ptr().unsafe_bitcast[UInt8]()
        var n_read = external_call["syscall", c_long](
            c_long(SYS_READ),
            c_int(fd),
            raw_ptr,
            UInt(bytes_to_read)
        )
        _ = external_call["close", c_int](fd)
        return n_read == c_long(bytes_to_read)

    def clone_state(self) raises -> RWKVStateBuffer:
        """
        Creates an in-memory clone of the recurrent state for speculative sandboxing.
        Mutations during dry-run validation can be evaluated in the fork and discarded.
        """
        var copy = RWKVStateBuffer(self.size)
        var src_ptr = self.data.unsafe_ptr().unsafe_bitcast[UInt8]()
        var dst_ptr = copy.data.unsafe_ptr().unsafe_bitcast[UInt8]()
        _ = external_call["memcpy", Pointer[NoneType, MutUntrackedOrigin]](
            dst_ptr,
            src_ptr,
            UInt(self.byte_size())
        )
        return copy^


struct RWKV7Runtime:
    """Manages the RWKV-7 inference runtime, recurrent state buffer, and temporal anchor."""
    var state: RWKVStateBuffer
    var is_librwkv_loaded: Bool
    var model_path: String

    def __init__(out self, default_state_dim: Int = 4096):
        # Default state dimension for testing/mock mode: 4096 elements
        self.state = RWKVStateBuffer(default_state_dim)
        self.is_librwkv_loaded = False
        self.model_path = ""

    def check_library_available(mut self, lib_path: String) -> Bool:
        var p = lib_path
        var handle = external_call["dlopen", c_long](
            p.as_c_string_span(),
            c_int(1) # RTLD_LAZY
        )
        if handle != 0:
            _ = external_call["dlclose", c_int](handle)
            self.is_librwkv_loaded = True
            return True
        return False

    def format_temporal_anchor(self, year: String = "2026") -> String:
        return "[SYSTEM_ANCHOR]\n" +
               "Current Date: " + year + "\n" +
               "Strict Rule: The current year is " + year + ". Do NOT assume earlier dates.\n" +
               "Temporal Rule: Any post-cutoff events MUST be verified via search.\n\n"

    def build_grounded_envelope(self, user_prompt: String, search_evidence: String = "") -> String:
        var anchor = self.format_temporal_anchor()
        var evidence_block = ""
        if search_evidence != "":
            evidence_block = "[VERIFIED_GROUND_TRUTH_SEARCH]\n" + search_evidence + "\n[END_GROUND_TRUTH]\n\n"
        return anchor + evidence_block + "User: " + user_prompt + "\nGoose:"


def main() raises:
    print("Testing RWKV7 Recurrent State Buffer...")
    var buf = RWKVStateBuffer(1024)
    print("Allocated State Elements:", buf.element_count())
    print("Byte Size:", buf.byte_size())

    # Test state clone
    var cloned = buf.clone_state()
    print("Cloned State Elements:", cloned.element_count())

    # Test atomic disk serialization
    var test_file = String("/tmp/rwkv7_test_state.bin")
    buf.save_to_disk(test_file)
    print("State saved atomically to:", test_file)

    var loaded = cloned.load_from_disk(test_file)
    print("State loaded from disk:", loaded)

    var rt = RWKV7Runtime()
    print("Grounded Envelope Check:\n" + rt.build_grounded_envelope("Check Linux kernel status"))
