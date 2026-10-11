"""Inspectable, conservative SGLang launch plans for the target AMD machine."""

import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from urllib.parse import urlparse

from .tools import bounded_process


def launch_plan(config, name):
    profile = config["models"][name]
    memory = config["hardware"]
    raw_gib = profile["parameters_b"] * 1e9 * profile["weight_bits"] / 8 / 2**30
    available = memory["unified_memory_gib"] - memory["reserve_memory_gib"]
    endpoint = urlparse(profile["endpoint"])
    argv = [sys.executable, "-m", "vllm.entrypoints.openai.api_server", "--model", profile["model_path"],
            "--host", "127.0.0.1", "--port", str(endpoint.port or 30000)] + profile.get("launch_args", [])
    if profile.get("served_model_name"):
        argv += ["--served-model-name", profile["served_model_name"]]
    issues = []
    if not profile["model_path"]:
        issues.append("Set an exact model_path first")
    if raw_gib >= available:
        issues.append("Raw weights exceed the configured memory budget; choose a supported quantized checkpoint or remote endpoint")
    if endpoint.hostname not in {"127.0.0.1", "localhost", "::1"}:
        issues.append("This is a remote endpoint; launch server on that remote host")
    return {"profile": name, "argv": argv, "raw_weight_gib": round(raw_gib, 2),
            "available_budget_gib": available, "issues": issues,
            "note": profile.get("note", "Kernel and memory availability must be checked on the target machine"),
            "memory_caveat": "Raw weights only; excludes KV/recurrent cache, quantization scales, activations and runtime. Fit is not proven."}


def doctor():
    result = {"os": platform.system(), "python": platform.python_version(),
              "vllm_installed": importlib.util.find_spec("vllm") is not None,
              "hyprctl": bool(shutil.which("hyprctl")), "rocminfo": bool(shutil.which("rocminfo")),
              "git": bool(shutil.which("git"))}
    if importlib.util.find_spec("torch"):
        script = """import json, torch
r={'torch':torch.__version__, 'hip':torch.version.hip, 'gpu_available':torch.cuda.is_available()}
if r['gpu_available']:
 p=torch.cuda.get_device_properties(0)
 r.update(device=p.name,total_memory_gib=p.total_memory/2**30,architecture=getattr(p,'gcnArchName',None))
 x=torch.ones((32,32),device='cuda'); r['matmul_ok']=bool((x@x==32).all().item())
print(json.dumps(r))
"""
        response = bounded_process([sys.executable, "-c", script], timeout=30)
        try:
            result["compute"] = json.loads(response["output"]) if response["ok"] else response
        except ValueError:
            result["compute"] = response
    else:
        result["compute"] = {"error": "Install the PyTorch ROCm build for this GPU in the SGLang environment"}
    result["ready_for_local_sglang"] = bool(result["os"] == "Linux" and result["sglang_installed"]
        and result["compute"].get("hip") and result["compute"].get("matmul_ok"))
    result["caveat"] = "A passing compute check does not validate model-specific SGLang kernels. Run probe after launch."
    return result


def serve(config, name, dry_run=False):
    plan = launch_plan(config, name)
    if dry_run:
        return plan
    if plan["issues"]:
        raise ValueError("; ".join(plan["issues"]))
    diagnostics = doctor()
    if not diagnostics["ready_for_local_sglang"]:
        raise ValueError("Local AMD SGLang preflight failed. Run aeon doctor in the ROCm environment")
    exposed = diagnostics["compute"].get("total_memory_gib", 0)
    if plan["raw_weight_gib"] >= exposed * 0.85:
        raise ValueError("GPU-visible memory is too small for these weights with runtime headroom; inspect aeon doctor")
    # Do not silently launch another large model beside an existing listener.
    import socket
    for profile in config["models"].values():
        endpoint = urlparse(profile["endpoint"])
        if endpoint.hostname not in {"127.0.0.1", "localhost", "::1"}:
            continue
        with socket.socket() as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", endpoint.port or 30000)) == 0:
                raise ValueError("A configured local model port is in use; stop that server before loading another model")
    return subprocess.call(plan["argv"], env=os.environ.copy())
