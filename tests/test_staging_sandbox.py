"""Comprehensive contract and confinement tests for Landlock sandboxing and dry-run staging."""
import ctypes
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

SYS_landlock_create_ruleset = 444
SYS_landlock_add_rule = 445
SYS_landlock_restrict_self = 446
PR_SET_NO_NEW_PRIVS = 38
LANDLOCK_RULE_PATH_BENEATH = 1

LANDLOCK_ACCESS_FS_EXECUTE = (1 << 0)
LANDLOCK_ACCESS_FS_WRITE_FILE = (1 << 1)
LANDLOCK_ACCESS_FS_READ_FILE = (1 << 2)
LANDLOCK_ACCESS_FS_READ_DIR = (1 << 3)
LANDLOCK_ACCESS_FS_REMOVE_DIR = (1 << 4)
LANDLOCK_ACCESS_FS_REMOVE_FILE = (1 << 5)
LANDLOCK_ACCESS_FS_MAKE_DIR = (1 << 7)
LANDLOCK_ACCESS_FS_MAKE_REG = (1 << 8)

READ_ONLY_ACCESS = LANDLOCK_ACCESS_FS_EXECUTE | LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_READ_DIR
WRITE_ACCESS = (
    LANDLOCK_ACCESS_FS_WRITE_FILE |
    LANDLOCK_ACCESS_FS_REMOVE_DIR |
    LANDLOCK_ACCESS_FS_REMOVE_FILE |
    LANDLOCK_ACCESS_FS_MAKE_DIR |
    LANDLOCK_ACCESS_FS_MAKE_REG
)
ALL_HANDLED = READ_ONLY_ACCESS | WRITE_ACCESS

class RulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]

class PathBeneathAttr(ctypes.Structure):
    _fields_ = [
        ("allowed_access", ctypes.c_uint64),
        ("parent_fd", ctypes.c_int32)
    ]


class StagingSandboxTests(unittest.TestCase):
    def test_landlock_kernel_abi(self):
        libc = ctypes.CDLL(None, use_errno=True)
        abi = libc.syscall(SYS_landlock_create_ruleset, 0, 0, 1)
        self.assertGreaterEqual(abi, 1, "Landlock must be supported by the host Linux kernel (ABI >= 1)")

    def test_landlock_filesystem_confinement(self):
        libc = ctypes.CDLL(None, use_errno=True)
        with tempfile.TemporaryDirectory(prefix="staging-write-") as allowed_dir:
            with tempfile.TemporaryDirectory(prefix="staging-blocked-") as blocked_dir:
                pid = os.fork()
                if pid == 0:
                    try:
                        attr = RulesetAttr(handled_access_fs=ALL_HANDLED)
                        ruleset_fd = libc.syscall(SYS_landlock_create_ruleset, ctypes.byref(attr), ctypes.sizeof(attr), 0)
                        if ruleset_fd < 0:
                            os._exit(10)

                        root_fd = os.open("/", os.O_PATH | os.O_DIRECTORY)
                        rule_root = PathBeneathAttr(allowed_access=READ_ONLY_ACCESS, parent_fd=root_fd)
                        if libc.syscall(SYS_landlock_add_rule, ruleset_fd, LANDLOCK_RULE_PATH_BENEATH, ctypes.byref(rule_root), 0) != 0:
                            os._exit(11)
                        os.close(root_fd)

                        allowed_fd = os.open(allowed_dir, os.O_PATH | os.O_DIRECTORY)
                        rule_allowed = PathBeneathAttr(allowed_access=READ_ONLY_ACCESS | WRITE_ACCESS, parent_fd=allowed_fd)
                        if libc.syscall(SYS_landlock_add_rule, ruleset_fd, LANDLOCK_RULE_PATH_BENEATH, ctypes.byref(rule_allowed), 0) != 0:
                            os._exit(12)
                        os.close(allowed_fd)

                        if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
                            os._exit(13)

                        if libc.syscall(SYS_landlock_restrict_self, ruleset_fd, 0) != 0:
                            os._exit(14)
                        os.close(ruleset_fd)

                        # Write to allowed dir must succeed
                        with open(os.path.join(allowed_dir, "staged.diff"), "w") as f:
                            f.write("valid diff")

                        # Write to blocked dir must fail with PermissionError
                        try:
                            with open(os.path.join(blocked_dir, "illegal.txt"), "w") as f:
                                f.write("should not succeed")
                            os._exit(20)
                        except PermissionError:
                            os._exit(0)
                    except Exception:
                        os._exit(99)
                else:
                    _, status = os.waitpid(pid, 0)
                    exit_code = os.waitstatus_to_exitcode(status)
                    self.assertEqual(exit_code, 0, "Landlock confinement must block unauthorized writes")

    def test_staging_dryrun_syntax_validation(self):
        with tempfile.TemporaryDirectory(prefix="staging-dryrun-") as staging_dir:
            # Stage valid Python file
            valid_file = Path(staging_dir) / "check_ok.py"
            valid_file.write_text("x = 42\ndef get_x():\n    return x\n")
            res = subprocess.run(["python", "-m", "py_compile", str(valid_file)], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, "Valid code must pass dry-run syntax compilation")

            # Stage invalid Python file
            invalid_file = Path(staging_dir) / "check_bad.py"
            invalid_file.write_text("def broken(:\n    return\n")
            res_bad = subprocess.run(["python", "-m", "py_compile", str(invalid_file)], capture_output=True, text=True)
            self.assertNotEqual(res_bad.returncode, 0, "Invalid code must fail dry-run syntax compilation")
            self.assertIn("SyntaxError", res_bad.stderr)

    def test_recurrent_state_serialization_lifecycle(self):
        with tempfile.TemporaryDirectory(prefix="rwkv-state-") as state_dir:
            state_file = Path(state_dir) / "test_state.bin"
            # 4096 Float32 elements = 16,384 bytes
            dummy_state = bytearray(16384)
            dummy_state[0:4] = b'\x00\x00\x80\x3f' # 1.0f in IEEE 754 float32

            # Atomic save via sibling .tmp file
            tmp_file = state_file.with_suffix('.tmp')
            tmp_file.write_bytes(dummy_state)
            os.replace(tmp_file, state_file)

            self.assertTrue(state_file.is_file())
            self.assertFalse(tmp_file.exists())
            self.assertEqual(state_file.stat().st_size, 16384)

            # Cold restore
            restored = state_file.read_bytes()
            self.assertEqual(len(restored), 16384)
            self.assertEqual(restored[0:4], b'\x00\x00\x80\x3f')


if __name__ == "__main__":
    unittest.main()
