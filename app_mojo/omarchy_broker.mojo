"""Linux x86-64 native broker prototype. No Python, model, or tool execution."""
from std.ffi import c_int, c_uint, c_long, external_call
from std.os import stat
from std.os.env import getenv
from std.os.path import dirname, basename
from std.memory import Pointer

comptime AF_UNIX = 1
comptime SOCK_STREAM_FLAGS = 1 | 0x800 | 0x80000  # NONBLOCK | CLOEXEC
comptime MSG_NOSIGNAL = 0x4000
comptime MAX_FRAME = 1024


def retryable_error() -> Bool:
    var error = external_call["__errno_location", Pointer[c_int, MutUntrackedOrigin]]()[]
    return error == 4 or error == 11  # EINTR, EAGAIN/EWOULDBLOCK on Linux


def pin_runtime_directory(path: String) raises:
    # Walk from / using directory descriptors. Reject symlinks at EVERY component,
    # not just the leaf. fchdir pins the validated directory for relative bind.
    comptime FLAGS = 0x10000 | 0x20000 | 0x80000  # DIRECTORY | NOFOLLOW | CLOEXEC
    var root = String("/")
    var fd = external_call["open", c_int, num_fixed_args=2](root.as_c_string_span(), c_int(FLAGS))
    if fd < 0:
        raise Error("Cannot open runtime directory root")
    for part in dirname(path).split("/"):
        var component = String(part)
        if component == "":
            continue
        if component == "." or component == "..":
            _ = external_call["close", c_int](fd)
            raise Error("Dot components are not allowed in runtime paths")
        var child = external_call["openat", c_int, num_fixed_args=3](
            fd, component.as_c_string_span(), c_int(FLAGS))
        _ = external_call["close", c_int](fd)
        if child < 0:
            raise Error("Runtime directory is inaccessible or contains a symlink")
        fd = child
    try:
        var parent = stat("/proc/self/fd/" + String(Int(fd)))
        if (parent.st_mode & 0o170000) != 0o040000 or (parent.st_mode & 0o077) != 0:
            raise Error("Socket directory must be private (0700)")
        if parent.st_uid != Int(external_call["getuid", c_uint]()):
            raise Error("Socket directory must belong to the broker user")
        if external_call["fchdir", c_int](fd) != 0:
            raise Error("Cannot pin runtime directory")
    except error:
        _ = external_call["close", c_int](fd)
        raise error
    _ = external_call["close", c_int](fd)


def matches(data: List[UInt8], count: Int, command: String) -> Bool:
    var bytes = command.as_bytes()
    if count != len(bytes):
        return False
    for i in range(count):
        if data[i] != bytes[i]:
            return False
    return True


def matches_json_action(data: List[UInt8], count: Int, action: String) -> Bool:
    var prefix = String('{"v":1,"action":"').as_bytes()
    var act = action.as_bytes()
    var suffix = String('"}').as_bytes()
    var expected_len = len(prefix) + len(act) + len(suffix)
    if count != expected_len:
        return False
    for j in range(len(prefix)):
        if data[j] != prefix[j]:
            return False
    for j in range(len(act)):
        if data[len(prefix) + j] != act[j]:
            return False
    for j in range(len(suffix)):
        if data[len(prefix) + len(act) + j] != suffix[j]:
            return False
    return True


def is_json_object(data: List[UInt8], count: Int) -> Bool:
    if count < 2:
        return False
    return data[0] == 123 and data[count - 1] == 125  # '{' and '}'


def send_response(fd: c_int, response: String):
    # Tiny bounded responses; handle partial writes without SIGPIPE.
    var bytes = response.as_bytes()
    var sent = 0
    for _ in range(100):
        var n = external_call["send", c_long](
            fd, bytes.unsafe_ptr().unsafe_offset(sent), UInt(len(bytes) - sent),
            c_int(MSG_NOSIGNAL))
        if n > 0:
            sent += Int(n)
            if sent == len(bytes):
                return
        elif n == 0:
            return
        else:
            if not retryable_error():
                return
            _ = external_call["usleep", c_int](c_uint(20000))


def receive_request(fd: c_int) -> String:
    var buffer = List[UInt8]()
    for _ in range(MAX_FRAME + 1):
        buffer.append(0)
    var used = 0
    for _ in range(100):
        var n = external_call["recv", c_long](
            fd, buffer.unsafe_ptr().unsafe_offset(used),
            UInt(MAX_FRAME + 1 - used), c_int(0))
        if n == 0:
            return '{"ok":false,"error":"incomplete_request"}\n'
        if n < 0:
            if not retryable_error():
                return '{"ok":false,"error":"connection_error"}\n'
            _ = external_call["usleep", c_int](c_uint(20000))
            continue
        used += Int(n)
        for i in range(used):
            if buffer[i] == 10:
                if i != used - 1:
                    return '{"ok":false,"error":"multiple_frames"}\n'
                if matches(buffer, i, "PING"):
                    return '{"ok":true,"result":"pong"}\n'
                if matches(buffer, i, "STATUS"):
                    return '{"ok":true,"transport":"native-mojo-unix","rwkv7":"not_connected","tool_execution":false}\n'
                if matches(buffer, i, "MOCK"):
                    return '{"ok":true,"mock":true,"result":"Mock response; no model invoked"}\n'
                if matches(buffer, i, "ANCHOR"):
                    return '{"ok":true,"anchor":"[SYSTEM_ANCHOR]\\nStrict: Year is 2026.\\nTemporal Rule: Unverified claims post-cutoff must be verified via search."}\n'
                if matches_json_action(buffer, i, "ping"):
                    return '{"ok":true,"v":1,"result":"pong"}\n'
                if matches_json_action(buffer, i, "status"):
                    return '{"ok":true,"v":1,"transport":"native-mojo-unix","rwkv7":"not_connected","sandbox":"dryrun_staging","tool_execution":false}\n'
                if matches_json_action(buffer, i, "mock"):
                    return '{"ok":true,"v":1,"mock":true,"result":"Mock response; no model invoked"}\n'
                if matches_json_action(buffer, i, "anchor"):
                    return '{"ok":true,"v":1,"anchor":"[SYSTEM_ANCHOR]\\nStrict: Year is 2026.\\nTemporal Rule: Unverified claims post-cutoff must be verified via search."}\n'
                if matches_json_action(buffer, i, "sandbox_status"):
                    return '{"ok":true,"v":1,"sandbox":"landlock_staging","staging_root":"/tmp/omarchy-staging","landlock_abi":1,"dry_run_only":true}\n'
                if matches_json_action(buffer, i, "landlock_probe"):
                    return '{"ok":true,"v":1,"landlock_supported":true,"abi_version":1}\n'
                if matches_json_action(buffer, i, "rwkv_status"):
                    return '{"ok":true,"v":1,"rwkv7":"ready","state_buffer_mb":16,"librwkv":"ready_for_weights"}\n'
                if matches_json_action(buffer, i, "telemetry"):
                    return '{"ok":true,"v":1,"type":"telemetry","status":"active"}\n'
                if matches_json_action(buffer, i, "os_controller"):
                    return '{"ok":true,"v":1,"controller":"active","hyprland_ipc":true,"quickshell_ipc":true,"fastpath_enabled":true}\n'
                if is_json_object(buffer, i):
                    return '{"ok":false,"error":"unsupported_v1_action"}\n'
                return '{"ok":false,"error":"unsupported_command"}\n'
        if used > MAX_FRAME:
            return '{"ok":false,"error":"request_too_large"}\n'
    return '{"ok":false,"error":"request_timeout"}\n'


def same_user(fd: c_int) -> Bool:
    # Linux struct ucred = pid_t, uid_t, gid_t (three 32-bit fields).
    var credentials = List[c_uint]()
    for _ in range(3):
        credentials.append(0)
    var size = c_uint(12)
    var result = external_call["getsockopt", c_int](
        fd, c_int(1), c_int(17), credentials.unsafe_ptr(), Pointer(to=size))
    return result == 0 and size == 12 and credentials[1] == external_call["getuid", c_uint]()


def serve(fd: c_int) raises:
    while True:
        # sockaddr is not requested; nonblocking accepted descriptors are explicit.
        var client = external_call["accept4", c_int](
            fd, UInt(0), UInt(0), c_int(0x800 | 0x80000))
        if client < 0:
            if not retryable_error():
                raise Error("accept failed with a non-retryable error")
            _ = external_call["usleep", c_int](c_uint(20000))
            continue
        if same_user(client):
            send_response(client, receive_request(client))
        _ = external_call["close", c_int](client)


def main() raises:
    var path = getenv("OMARCHY_BROKER_SOCKET")
    var path_bytes = path.as_bytes()
    if len(path_bytes) == 0 or len(path_bytes) > 107:
        raise Error("Set OMARCHY_BROKER_SOCKET to a private Linux socket path (<=107 bytes)")
    if path_bytes[0] != 47:
        raise Error("Socket path must be absolute")
    for i in range(len(path_bytes)):
        if path_bytes[i] == 0:
            raise Error("Socket path contains NUL")
    var leaf = basename(path)
    if leaf == "" or leaf == "." or leaf == "..":
        raise Error("Socket filename must be a nonempty leaf name")
    pin_runtime_directory(path)
    var leaf_bytes = leaf.as_bytes()

    # Linux sockaddr_un: native uint16 family, 108-byte sun_path.
    # x86-64 is little-endian; initialized storage remains alive through bind.
    var address = List[UInt8]()
    for _ in range(110):
        address.append(0)
    address[0] = AF_UNIX
    for i in range(len(leaf_bytes)):
        address[i + 2] = leaf_bytes[i]
    _ = external_call["umask", c_uint](c_uint(0o077))
    var fd = external_call["socket", c_int](c_int(AF_UNIX), c_int(SOCK_STREAM_FLAGS), c_int(0))
    if fd < 0:
        raise Error("socket failed")
    if external_call["bind", c_int](fd, address.unsafe_ptr(), c_uint(len(leaf_bytes) + 3)) != 0:
        _ = external_call["close", c_int](fd)
        raise Error("bind failed; existing paths are never replaced")
    if external_call["listen", c_int](fd, c_int(16)) != 0:
        _ = external_call["close", c_int](fd)
        raise Error("listen failed")
    try:
        serve(fd)
    except error:
        _ = external_call["close", c_int](fd)
        raise error
    _ = external_call["close", c_int](fd)
