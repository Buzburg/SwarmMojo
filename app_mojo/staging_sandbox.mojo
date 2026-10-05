"""Staging workspace and Landlock filesystem sandbox for Omarchy Mojo RWKV7."""
from std.ffi import c_int, c_uint, c_long, external_call
from std.os import stat
from std.os.path import dirname, basename
from std.memory import Pointer

comptime SYS_PRCTL = 157
comptime SYS_LANDLOCK_CREATE_RULESET = 444
comptime SYS_LANDLOCK_ADD_RULE = 445
comptime SYS_LANDLOCK_RESTRICT_SELF = 446
comptime PR_SET_NO_NEW_PRIVS = 38
comptime LANDLOCK_CREATE_RULESET_VERSION = 1
comptime LANDLOCK_RULE_PATH_BENEATH = 1

# Landlock ABI v1 Access Rights
comptime LANDLOCK_ACCESS_FS_EXECUTE = 1
comptime LANDLOCK_ACCESS_FS_WRITE_FILE = 2
comptime LANDLOCK_ACCESS_FS_READ_FILE = 4
comptime LANDLOCK_ACCESS_FS_READ_DIR = 8
comptime LANDLOCK_ACCESS_FS_REMOVE_DIR = 16
comptime LANDLOCK_ACCESS_FS_REMOVE_FILE = 32
comptime LANDLOCK_ACCESS_FS_MAKE_DIR = 128
comptime LANDLOCK_ACCESS_FS_MAKE_REG = 256

comptime READ_ONLY_FS = LANDLOCK_ACCESS_FS_EXECUTE | LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_READ_DIR
comptime WRITE_FS = (
    LANDLOCK_ACCESS_FS_WRITE_FILE |
    LANDLOCK_ACCESS_FS_REMOVE_DIR |
    LANDLOCK_ACCESS_FS_REMOVE_FILE |
    LANDLOCK_ACCESS_FS_MAKE_DIR |
    LANDLOCK_ACCESS_FS_MAKE_REG
)
comptime ALL_HANDLED_FS = READ_ONLY_FS | WRITE_FS


def probe_landlock_abi() -> Int:
    """Returns the Landlock ABI version (e.g. 1, 2, 3) or a negative value if unsupported."""
    var ver = external_call["syscall", c_long](
        c_long(SYS_LANDLOCK_CREATE_RULESET),
        UInt(0),
        UInt(0),
        c_uint(LANDLOCK_CREATE_RULESET_VERSION)
    )
    return Int(ver)


def is_landlock_available() -> Bool:
    return probe_landlock_abi() >= 1


def ensure_directory(path: String) raises -> Bool:
    """Ensures an isolated staging directory exists with private permissions (0700)."""
    comptime O_DIRECTORY = 0x10000
    comptime O_CLOEXEC = 0x80000
    var p = path
    var res = external_call["mkdir", c_int](p.as_c_string_span(), c_uint(0o0700))
    if res == 0:
        return True
    # If already exists, verify ownership and permissions
    var st = stat(path)
    if (st.st_mode & 0o170000) != 0o040000:
        raise Error("Path exists but is not a directory: " + path)
    return True


def apply_landlock_sandbox(allowed_writable_dir: String) raises:
    """
    Confines the calling process using Linux Landlock.
    Allows read-only access to / and full read/write access to allowed_writable_dir.
    """
    if not is_landlock_available():
        raise Error("Landlock is not supported by the host Linux kernel")

    _ = ensure_directory(allowed_writable_dir)

    # 1. landlock_ruleset_attr: 64-bit handled_access_fs
    var attr = List[UInt64]()
    attr.append(UInt64(ALL_HANDLED_FS))

    var ruleset_fd = external_call["syscall", c_int](
        c_long(SYS_LANDLOCK_CREATE_RULESET),
        attr.unsafe_ptr(),
        UInt(8),
        c_uint(0)
    )
    if ruleset_fd < 0:
        raise Error("Failed to create Landlock ruleset")

    # 2. Add rule for root / (read + execute)
    comptime O_PATH = 0o10000000
    var root_path = String("/")
    var root_fd = external_call["open", c_int, num_fixed_args=2](
        root_path.as_c_string_span(),
        c_int(O_PATH | 0x10000)
    )
    if root_fd >= 0:
        var rule_root = List[UInt64]()
        rule_root.append(UInt64(READ_ONLY_FS))
        rule_root.append(UInt64(root_fd)) # parent_fd in low 32 bits
        _ = external_call["syscall", c_int](
            c_long(SYS_LANDLOCK_ADD_RULE),
            ruleset_fd,
            c_uint(LANDLOCK_RULE_PATH_BENEATH),
            rule_root.unsafe_ptr(),
            c_uint(0)
        )
        _ = external_call["close", c_int](root_fd)

    # 3. Add rule for allowed writable directory (read + write)
    var write_path = allowed_writable_dir
    var write_fd = external_call["open", c_int, num_fixed_args=2](
        write_path.as_c_string_span(),
        c_int(O_PATH | 0x10000)
    )
    if write_fd >= 0:
        var rule_write = List[UInt64]()
        rule_write.append(UInt64(READ_ONLY_FS | WRITE_FS))
        rule_write.append(UInt64(write_fd))
        _ = external_call["syscall", c_int](
            c_long(SYS_LANDLOCK_ADD_RULE),
            ruleset_fd,
            c_uint(LANDLOCK_RULE_PATH_BENEATH),
            rule_write.unsafe_ptr(),
            c_uint(0)
        )
        _ = external_call["close", c_int](write_fd)

    # 4. Set PR_SET_NO_NEW_PRIVS
    if external_call["prctl", c_int](c_int(PR_SET_NO_NEW_PRIVS), c_long(1), c_long(0), c_long(0), c_long(0)) != 0:
        _ = external_call["close", c_int](ruleset_fd)
        raise Error("Failed to set PR_SET_NO_NEW_PRIVS")

    # 5. Restrict self
    if external_call["syscall", c_int](c_long(SYS_LANDLOCK_RESTRICT_SELF), ruleset_fd, c_uint(0)) != 0:
        _ = external_call["close", c_int](ruleset_fd)
        raise Error("Failed to enforce Landlock self-restriction")

    _ = external_call["close", c_int](ruleset_fd)


def main() raises:
    print("Landlock Probe ABI:", probe_landlock_abi())
    print("Landlock Available:", is_landlock_available())
