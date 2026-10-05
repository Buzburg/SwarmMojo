"""Verify Landlock sandbox execution in Python before Mojo implementation."""
import ctypes
import os
import stat
import sys
import tempfile

SYS_landlock_create_ruleset = 444
SYS_landlock_add_rule = 445
SYS_landlock_restrict_self = 446
PR_SET_NO_NEW_PRIVS = 38
LANDLOCK_RULE_PATH_BENEATH = 1

# Landlock ABI v1 handled access rights
LANDLOCK_ACCESS_FS_EXECUTE = (1 << 0)
LANDLOCK_ACCESS_FS_WRITE_FILE = (1 << 1)
LANDLOCK_ACCESS_FS_READ_FILE = (1 << 2)
LANDLOCK_ACCESS_FS_READ_DIR = (1 << 3)
LANDLOCK_ACCESS_FS_REMOVE_DIR = (1 << 4)
LANDLOCK_ACCESS_FS_REMOVE_FILE = (1 << 5)
LANDLOCK_ACCESS_FS_MAKE_CHAR = (1 << 6)
LANDLOCK_ACCESS_FS_MAKE_DIR = (1 << 7)
LANDLOCK_ACCESS_FS_MAKE_REG = (1 << 8)
LANDLOCK_ACCESS_FS_MAKE_SOCK = (1 << 9)
LANDLOCK_ACCESS_FS_MAKE_FIFO = (1 << 10)
LANDLOCK_ACCESS_FS_MAKE_BLOCK = (1 << 11)
LANDLOCK_ACCESS_FS_MAKE_SYM = (1 << 12)

ALL_ACCESS_FS = (
    LANDLOCK_ACCESS_FS_EXECUTE |
    LANDLOCK_ACCESS_FS_WRITE_FILE |
    LANDLOCK_ACCESS_FS_READ_FILE |
    LANDLOCK_ACCESS_FS_READ_DIR |
    LANDLOCK_ACCESS_FS_REMOVE_DIR |
    LANDLOCK_ACCESS_FS_REMOVE_FILE |
    LANDLOCK_ACCESS_FS_MAKE_CHAR |
    LANDLOCK_ACCESS_FS_MAKE_DIR |
    LANDLOCK_ACCESS_FS_MAKE_REG |
    LANDLOCK_ACCESS_FS_MAKE_SOCK |
    LANDLOCK_ACCESS_FS_MAKE_FIFO |
    LANDLOCK_ACCESS_FS_MAKE_BLOCK |
    LANDLOCK_ACCESS_FS_MAKE_SYM
)

READ_EXEC_ACCESS = (
    LANDLOCK_ACCESS_FS_EXECUTE |
    LANDLOCK_ACCESS_FS_READ_FILE |
    LANDLOCK_ACCESS_FS_READ_DIR
)

WRITE_ACCESS = (
    LANDLOCK_ACCESS_FS_WRITE_FILE |
    LANDLOCK_ACCESS_FS_REMOVE_DIR |
    LANDLOCK_ACCESS_FS_REMOVE_FILE |
    LANDLOCK_ACCESS_FS_MAKE_DIR |
    LANDLOCK_ACCESS_FS_MAKE_REG |
    LANDLOCK_ACCESS_FS_MAKE_SOCK |
    LANDLOCK_ACCESS_FS_MAKE_SYM
)

class RulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]

class PathBeneathAttr(ctypes.Structure):
    _fields_ = [
        ("allowed_access", ctypes.c_uint64),
        ("parent_fd", ctypes.c_int32)
    ]

def test_landlock_confinement():
    libc = ctypes.CDLL(None, use_errno=True)
    
    # 1. Create temporary directory that should be writeable
    with tempfile.TemporaryDirectory(prefix="landlock-write-") as allowed_dir:
        # Create temporary directory that should NOT be writeable
        with tempfile.TemporaryDirectory(prefix="landlock-blocked-") as blocked_dir:
            pid = os.fork()
            if pid == 0:
                try:
                    # Child process: apply Landlock
                    attr = RulesetAttr(handled_access_fs=ALL_ACCESS_FS)
                    ruleset_fd = libc.syscall(
                        SYS_landlock_create_ruleset,
                        ctypes.byref(attr),
                        ctypes.sizeof(attr),
                        0
                    )
                    if ruleset_fd < 0:
                        os._exit(10)

                    # Allow read everywhere on root /
                    root_fd = os.open("/", os.O_PATH | os.O_DIRECTORY)
                    rule_root = PathBeneathAttr(
                        allowed_access=READ_EXEC_ACCESS,
                        parent_fd=root_fd
                    )
                    r = libc.syscall(
                        SYS_landlock_add_rule,
                        ruleset_fd,
                        LANDLOCK_RULE_PATH_BENEATH,
                        ctypes.byref(rule_root),
                        0
                    )
                    os.close(root_fd)
                    if r != 0:
                        os._exit(11)

                    # Allow read + write only in allowed_dir
                    allowed_fd = os.open(allowed_dir, os.O_PATH | os.O_DIRECTORY)
                    rule_allowed = PathBeneathAttr(
                        allowed_access=READ_EXEC_ACCESS | WRITE_ACCESS,
                        parent_fd=allowed_fd
                    )
                    r = libc.syscall(
                        SYS_landlock_add_rule,
                        ruleset_fd,
                        LANDLOCK_RULE_PATH_BENEATH,
                        ctypes.byref(rule_allowed),
                        0
                    )
                    os.close(allowed_fd)
                    if r != 0:
                        os._exit(12)

                    # prctl(PR_SET_NO_NEW_PRIVS, 1)
                    if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
                        os._exit(13)

                    # Restrict self
                    if libc.syscall(SYS_landlock_restrict_self, ruleset_fd, 0) != 0:
                        os._exit(14)
                    os.close(ruleset_fd)

                    # Now test: writing to allowed_dir MUST SUCCEED
                    test_file_allowed = os.path.join(allowed_dir, "test.txt")
                    with open(test_file_allowed, "w") as f:
                        f.write("allowed write ok")

                    # Now test: writing to blocked_dir MUST FAIL with EACCES / PermissionError
                    test_file_blocked = os.path.join(blocked_dir, "test.txt")
                    try:
                        with open(test_file_blocked, "w") as f:
                            f.write("should fail")
                        os._exit(20) # Failure: write succeeded when it should have failed
                    except PermissionError:
                        # Success: Landlock blocked the unauthorized write!
                        os._exit(0)
                except Exception as ex:
                    print("Child exception:", ex)
                    os._exit(99)
            else:
                _, status = os.waitpid(pid, 0)
                exit_code = os.waitstatus_to_exitcode(status)
                return exit_code

if __name__ == "__main__":
    result = test_landlock_confinement()
    print("Landlock Confinement Test Result Code:", result)
    if result == 0:
        print("PASS: Landlock actively blocked unauthorized filesystem write!")
    else:
        print(f"FAIL: Exit code {result}")
    sys.exit(result)
