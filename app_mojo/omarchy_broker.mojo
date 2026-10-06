"""Native authenticated socket transport with Python JSON and ROMS integration."""
from std.python import Python, PythonObject
from std.ffi import c_int, c_uint, c_long, external_call
from std.os import stat
from std.os.env import getenv
from std.os.path import dirname, basename
from std.memory import Pointer

comptime AF_UNIX = 1
comptime SOCK_STREAM_FLAGS = 1 | 0x800 | 0x80000  # NONBLOCK | CLOEXEC
comptime MSG_NOSIGNAL = 0x4000
comptime MAX_FRAME = 65536
comptime MAX_CONNECTIONS = 16


def monotonic_milliseconds() raises -> Int:
    var stamp = List[c_long]()
    stamp.append(0)
    stamp.append(0)
    if external_call["clock_gettime", c_int](c_int(1), stamp.unsafe_ptr()) != 0:
        raise Error("Cannot read monotonic clock")
    return Int(stamp[0]) * 1000 + Int(stamp[1]) // 1000000


def transport_error(code: String, message: String) raises -> String:
    var protocol = Python.import_module("app.broker_protocol")
    return String(protocol.encode(protocol.error_response(code, message)))


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


struct Client(Movable):
    var fd: c_int
    var buffer: List[UInt8]
    var used: Int
    var deadline: Int
    var phase: Int  # 0 frame, 1 asynchronous action, 2 response.
    var token: Int
    var response: String
    var sent: Int

    def __init__(out self, fd: c_int, now: Int):
        self.fd = fd
        self.buffer = List[UInt8]()
        for _ in range(MAX_FRAME + 1):
            self.buffer.append(0)
        self.used = 0
        self.deadline = now + 5000
        self.phase = 0
        self.token = -1
        self.response = String("")
        self.sent = 0

    def reply(mut self, response: String, now: Int):
        self.response = response
        self.phase = 2
        self.deadline = now + 2000


def peer_gone(fd: c_int) -> Bool:
    # Linux x86-64 pollfd: s32 fd, s16 events, s16 revents. HUP distinguishes
    # a closed peer from a legitimate write-half-close awaiting its response.
    var pollfd = List[c_int]()
    pollfd.append(fd)
    pollfd.append(0)
    var result = external_call["poll", c_int](pollfd.unsafe_ptr(), UInt(1), c_int(0))
    return result > 0 and (Int(pollfd[1]) >> 16) & 0x38 != 0


def drive(mut client: Client, scheduler: PythonObject, now: Int) raises -> Bool:
    if client.phase == 0:
        if now >= client.deadline:
            client.reply(transport_error("REQUEST_TIMEOUT", "Request frame was not completed within five seconds"), now)
        else:
            var n = external_call["recv", c_long](client.fd,
                client.buffer.unsafe_ptr().unsafe_offset(client.used), UInt(MAX_FRAME + 1 - client.used), c_int(0))
            if n == 0:
                client.reply(transport_error("INCOMPLETE_REQUEST", "Connection closed before a complete frame"), now)
            elif n < 0:
                if not retryable_error():
                    return False
            else:
                var previous = client.used
                client.used += Int(n)
                for i in range(previous, client.used):
                    if client.buffer[i] == 10:
                        if i != client.used - 1:
                            client.reply(transport_error("MULTIPLE_FRAMES", "Only one frame is accepted per connection"), now)
                            break
                        var builtins = Python.import_module("builtins")
                        var frame = builtins.bytearray()
                        for j in range(i):
                            _ = frame.append(Int(client.buffer[j]))
                        var submitted = scheduler.submit(frame)
                        client.token = Int(py=submitted[0])
                        if client.token < 0:
                            client.reply(String(submitted[1]), now)
                        else:
                            client.phase = 1
                        break
                if client.phase == 0 and client.used > MAX_FRAME:
                    client.reply(transport_error("REQUEST_TOO_LARGE", "Request exceeds the 65536-byte frame limit"), now)
    if client.phase == 1:
        if peer_gone(client.fd):
            _ = scheduler.detach(client.token)
            return False
        if Bool(scheduler.ready(client.token)):
            client.reply(String(scheduler.take(client.token)), now)
    if client.phase == 2:
        if now >= client.deadline:
            return False
        var bytes = client.response.as_bytes()
        var n = external_call["send", c_long](client.fd, bytes.unsafe_ptr().unsafe_offset(client.sent),
                                            UInt(len(bytes) - client.sent), c_int(MSG_NOSIGNAL))
        if n > 0:
            client.sent += Int(n)
            return client.sent < len(bytes)
        if n == 0 or not retryable_error():
            return False
    return True


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
    var module = Python.import_module("app.broker_scheduler")
    var scheduler = module.Scheduler()
    var clients = List[Client]()
    try:
        while True:
            _ = scheduler.tick()
            var now = monotonic_milliseconds()
            var i = 0
            while i < len(clients):
                if not drive(clients[i], scheduler, now):
                    _ = external_call["close", c_int](clients[i].fd)
                    _ = clients.pop(i)
                else:
                    i += 1
            # Bound acceptance per iteration so traffic cannot starve active work.
            for _ in range(MAX_CONNECTIONS):
                var client = external_call["accept4", c_int](fd, UInt(0), UInt(0), c_int(0x800 | 0x80000))
                if client < 0:
                    if not retryable_error():
                        raise Error("accept failed with a non-retryable error")
                    break
                if same_user(client) and len(clients) < MAX_CONNECTIONS:
                    clients.append(Client(client, monotonic_milliseconds()))
                else:
                    if same_user(client):
                        send_response(client, transport_error("QUEUE_FULL", "The broker connection limit is reached"))
                    _ = external_call["close", c_int](client)
            _ = external_call["usleep", c_int](c_uint(10000))
    except error:
        for i in range(len(clients)):
            _ = external_call["close", c_int](clients[i].fd)
        _ = scheduler.close()
        raise error


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
