"""Master verification runner for the entire Omarchy Mojo RWKV7 Harness and ROMS."""
import os
from pathlib import Path
import subprocess
import sys
import time

def run_step(title: str, cmd: list[str], cwd: str | None = None, env: dict | None = None) -> tuple[bool, str, float]:
    print(f"\n[RUNNING] {title}...")
    t0 = time.monotonic()
    try:
        run_env = os.environ.copy()
        if env:
            run_env.update(env)
        res = subprocess.run(cmd, cwd=cwd, env=run_env, capture_output=True, text=True, timeout=60)
        elapsed = time.monotonic() - t0
        output = (res.stdout + "\n" + res.stderr).strip()
        if res.returncode == 0:
            print(f"[✓ PASS] {title} ({elapsed:.2f}s)")
            return True, output, elapsed
        else:
            print(f"[✗ FAIL] {title} (code {res.returncode}, {elapsed:.2f}s)")
            return False, output, elapsed
    except Exception as e:
        elapsed = time.monotonic() - t0
        print(f"[✗ ERROR] {title}: {e}")
        return False, str(e), elapsed

def main():
    print("=" * 75)
    print(" Omarchy Mojo RWKV7 Harness & ROMS Master Verification Suite")
    print("=" * 75)
    
    root_dir = Path(__file__).resolve().parent.parent
    results = []

    # 1. Environment & Landlock Probe
    results.append(("Kernel & Hardware Capabilities", *run_step("Hardware & Landlock Probe", [sys.executable, "scripts/probe_environment.py"], cwd=str(root_dir))))

    # 2. Landlock Sandboxing & Staging Tests
    results.append(("Landlock & Staging Sandbox Suite", *run_step("Landlock & Staging Unit Tests", [sys.executable, "-m", "unittest", "tests/test_staging_sandbox.py", "-v"], cwd=str(root_dir))))

    # 3. Native Broker Protocol Suite
    broker_bin = root_dir / ".pixi/envs/default/bin/omarchy-broker"
    if broker_bin.is_file():
        results.append(("Native Broker Protocol (21 Tests)", *run_step("Native Socket Protocol Tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_omarchy_broker.py", "-v"], cwd=str(root_dir), env={"OMARCHY_BROKER_BINARY": str(broker_bin)})))
    else:
        print("[!] Native broker binary not found; run pixi run build-broker first.")

    # 4. RWKV-7 Engine Native Binary Execution
    rwkv_bin = root_dir / ".pixi/envs/default/bin/rwkv-engine"
    if not rwkv_bin.is_file() and Path("/tmp/rwkv-engine").is_file():
        rwkv_bin = Path("/tmp/rwkv-engine")
    if rwkv_bin.is_file():
        results.append(("RWKV-7 Native State Engine", *run_step("RWKV-7 Recurrent State Lifecycle", [str(rwkv_bin)], cwd=str(root_dir))))

    # 5. Landlock Staging Native Binary Execution
    staging_bin = root_dir / ".pixi/envs/default/bin/staging-sandbox"
    if not staging_bin.is_file() and Path("/tmp/staging-sandbox").is_file():
        staging_bin = Path("/tmp/staging-sandbox")
    if staging_bin.is_file():
        results.append(("Landlock Staging Native Binary", *run_step("Native Landlock Staging Probe", [str(staging_bin)], cwd=str(root_dir))))

    # 6. OS Controller Native Binary Execution
    ctrl_bin = root_dir / ".pixi/envs/default/bin/os-controller"
    if not ctrl_bin.is_file() and Path("/tmp/os-controller").is_file():
        ctrl_bin = Path("/tmp/os-controller")
    if ctrl_bin.is_file():
        results.append(("OS Controller & Fast-Path Dispatcher", *run_step("OS Controller & Telemetry Engine", [str(ctrl_bin)], cwd=str(root_dir))))

    # 7. RWKV-7 Downloader Dry-Run Check
    results.append(("RWKV-7 Checkpoint Downloader (Dry-Run)", *run_step("Downloader Catalog & Path Verification", [sys.executable, "scripts/download_rwkv7.py", "--dry-run"], cwd=str(root_dir))))

    # Summary
    print("\n" + "=" * 75)
    print(" Master Verification Summary")
    print("=" * 75)
    total_passed = sum(1 for _, ok, _, _ in results if ok)
    total_tests = len(results)

    for name, ok, _, dur in results:
        status = "[PASS]" if ok else "[FAIL]"
        print(f" {status:6} | {dur:5.2f}s | {name}")
    print("-" * 75)
    print(f" Total Completed: {total_passed}/{total_tests} suites passed cleanly.")
    print("=" * 75)

    if total_passed < total_tests:
        sys.exit(1)

if __name__ == "__main__":
    main()
