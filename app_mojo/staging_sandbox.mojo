"""Linux x86-64 Landlock boundary; compose with the rootless worker policy."""
from std.ffi import c_int, c_uint, c_long, external_call
from std.os import stat
from std.sys import argv

comptime MIN_ABI = 3  # REFER (v2) and TRUNCATE (v3) are required.
comptime READ_EXEC = (1 << 0) | (1 << 2) | (1 << 3)
comptime HANDLED_V3 = (1 << 15) - 1
comptime WRITE_STAGE = (1 << 1) | (1 << 4) | (1 << 5) | (1 << 7) | (1 << 8) | (1 << 9) | (1 << 10) | (1 << 12) | (1 << 13) | (1 << 14)
comptime DIR_FLAGS = 0x10000 | 0x20000 | 0x80000  # DIRECTORY | NOFOLLOW | CLOEXEC


def probe_landlock_abi() -> Int:
    return Int(external_call["syscall", c_long, num_fixed_args=1](
        c_long(444), c_long(0), c_long(0), c_long(1)))


def is_landlock_available() -> Bool:
    return probe_landlock_abi() >= MIN_ABI


def pin_stage(path: String) raises -> c_int:
    if not path.startswith("/") or path == "/":
        raise Error("Stage must be an absolute non-root directory")
    var root = String("/")
    var fd = external_call["open", c_int, num_fixed_args=2](root.as_c_string_span(), c_int(DIR_FLAGS))
    if fd < 0:
        raise Error("Cannot pin filesystem root")
    for part in path.split("/"):
        var component = String(part)
        if component == "":
            continue
        if component == "." or component == "..":
            _ = external_call["close", c_int](fd)
            raise Error("Dot components are forbidden in staging paths")
        var child = external_call["openat", c_int, num_fixed_args=3](
            fd, component.as_c_string_span(), c_int(DIR_FLAGS))
        _ = external_call["close", c_int](fd)
        if child < 0:
            raise Error("Stage path is missing, inaccessible or contains a symlink")
        fd = child
    try:
        var info = stat("/proc/self/fd/" + String(Int(fd)))
        if info.st_uid != Int(external_call["getuid", c_uint]()):
            raise Error("Stage must belong to the worker user")
        if (info.st_mode & 0o170000) != 0o040000 or (info.st_mode & 0o077) != 0:
            raise Error("Stage directory must be private (0700)")
    except error:
        _ = external_call["close", c_int](fd)
        raise error
    return fd


def add_path_rule(ruleset: c_int, fd: c_int, access: UInt64) raises:
    # Packed u64 rights + s32 fd; the kernel ignores the trailing four bytes.
    var rule = List[UInt64]()
    rule.append(access)
    rule.append(UInt64(fd))
    if external_call["syscall", c_long, num_fixed_args=1](
        c_long(445), c_long(ruleset), c_long(1), rule.unsafe_ptr(), c_long(0)) != 0:
        raise Error("Landlock path rule installation failed")


def apply_landlock_sandbox(stage_fd: c_int) raises:
    var abi = probe_landlock_abi()
    if abi < MIN_ABI:
        raise Error("Landlock ABI 3 or newer is required for truncate and rename protection")
    var handled = UInt64(HANDLED_V3)
    if abi >= 5:
        handled |= UInt64(1 << 15)  # Deny device ioctl where supported.
    var attr = List[UInt64]()
    attr.append(handled)
    var ruleset = c_int(external_call["syscall", c_long, num_fixed_args=1](
        c_long(444), attr.unsafe_ptr(), c_long(8), c_long(0)))
    if ruleset < 0:
        raise Error("Landlock ruleset creation failed")
    try:
        # Only the system toolchain is readable/executable outside the stage.
        var usr = String("/usr")
        var usr_fd = external_call["open", c_int, num_fixed_args=2](usr.as_c_string_span(), c_int(DIR_FLAGS))
        if usr_fd < 0:
            raise Error("Read-only system toolchain is unavailable")
        try:
            add_path_rule(ruleset, usr_fd, UInt64(READ_EXEC))
        finally:
            _ = external_call["close", c_int](usr_fd)
        add_path_rule(ruleset, stage_fd, UInt64(READ_EXEC | WRITE_STAGE))
        if external_call["prctl", c_int, num_fixed_args=1](
            c_int(38), c_long(1), c_long(0), c_long(0), c_long(0)) != 0:
            raise Error("Cannot set no-new-privileges")
        if external_call["syscall", c_long, num_fixed_args=1](
            c_long(446), c_long(ruleset), c_long(0)) != 0:
            raise Error("Landlock enforcement failed")
    finally:
        _ = external_call["close", c_int](ruleset)


def main() raises:
    var args = argv()
    if len(args) == 2 and args[1] == "--probe":
        print(probe_landlock_abi())
        return
    if len(args) < 4 or args[2] != "--":
        raise Error("Usage: staging-sandbox STAGE -- /absolute/program [arguments]")
    var command = List[String]()
    for i in range(3, len(args)):
        command.append(String(args[i]))
    if not command[0].startswith("/"):
        raise Error("An absolute executable path is required")
    var pointers = List[UInt]()
    for i in range(len(command)):
        pointers.append(UInt(Int(command[i].as_c_string_span().ptr())))
    pointers.append(0)
    var stage_fd = pin_stage(String(args[1]))
    try:
        apply_landlock_sandbox(stage_fd)
        if external_call["fchdir", c_int](stage_fd) != 0:
            raise Error("Cannot enter pinned stage")
    finally:
        _ = external_call["close", c_int](stage_fd)
    if external_call["clearenv", c_int]() != 0:
        raise Error("Cannot clear worker environment")
    if external_call["syscall", c_long, num_fixed_args=1](
        c_long(436), c_long(3), c_long(0xffffffff), c_long(0)) != 0:
        raise Error("Cannot close inherited descriptors")
    _ = external_call["execv", c_int](command[0].as_c_string_span(), pointers.unsafe_ptr())
    raise Error("Cannot execute the confined command")
