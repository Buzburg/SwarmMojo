"""Probe Linux environment capabilities: Landlock, CPU features, VRAM, and Mojo toolchain."""
import ctypes
import os
import platform
import subprocess
import sys

def probe_landlock() -> dict:
    SYS_landlock_create_ruleset = 444
    LANDLOCK_CREATE_RULESET_VERSION = (1 << 0)
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        res = libc.syscall(SYS_landlock_create_ruleset, 0, 0, LANDLOCK_CREATE_RULESET_VERSION)
        errno = ctypes.get_errno()
        if res >= 1:
            return {"supported": True, "abi_version": res}
        else:
            return {"supported": False, "errno": errno, "reason": "ENOSYS or disabled in kernel"}
    except Exception as e:
        return {"supported": False, "error": str(e)}

def probe_system() -> dict:
    uname = platform.uname()
    cpu_info = {}
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if ":" in line:
                    k, v = line.split(":", 1)
                    k = k.strip()
                    if k in ("model name", "flags"):
                        if k not in cpu_info:
                            cpu_info[k] = v.strip()
    except Exception:
        pass
    
    mem_total_mb = 0
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_total_mb = int(line.split()[1]) // 1024
                    break
    except Exception:
        pass

    landlock = probe_landlock()
    return {
        "os": uname.system,
        "release": uname.release,
        "machine": uname.machine,
        "cpu_model": cpu_info.get("model name", "Unknown"),
        "avx2": "avx2" in cpu_info.get("flags", ""),
        "avx512": "avx512" in cpu_info.get("flags", ""),
        "mem_total_mb": mem_total_mb,
        "landlock": landlock
    }

if __name__ == "__main__":
    import json
    data = probe_system()
    print(json.dumps(data, indent=2))
