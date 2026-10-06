"""Evidence-aware sequential DAG execution for trusted local commands."""

from __future__ import annotations

import hashlib
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from ._support import canonical, load, mapping, number, strings, text

MAX_LOG = 5 * 1024 * 1024


@dataclass(frozen=True)
class Step:
    id: str
    command: list[str]
    verify: list[str]
    needs: list[str]
    inputs: list[str]
    outputs: list[str]
    timeout: float
    cache: bool


def inside(root: Path, name: str) -> Path:
    candidate = Path(name)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise ValueError(f"Expected a relative file path: {name}")
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root) or ".workflowproof" in candidate.parts:
        raise ValueError(f"Path escapes workspace or targets internal evidence: {name}")
    return resolved


def parse(manifest: dict[str, object], root: Path) -> tuple[list[Step], float]:
    if manifest.get("version") != 1:
        raise ValueError("Manifest version must be 1.")
    raw = manifest.get("steps")
    if not isinstance(raw, list) or not raw or len(raw) > 100:
        raise ValueError("Provide 1–100 steps.")
    steps: dict[str, Step] = {}
    owners: dict[Path, str] = {}
    for value in raw:
        item = mapping(value, "step")
        identifier = text(item.get("id"), "id")
        if re.fullmatch("[a-zA-Z0-9_-]{1,64}", identifier) is None or identifier in steps:
            raise ValueError("Step IDs must be unique and use letters, digits, underscores or hyphens.")
        command = strings(item.get("command"), "command")
        verify = strings(item.get("verify"), "verify")
        outputs = strings(item.get("outputs"), "outputs")
        if not command or not verify or not outputs:
            raise ValueError(f"{identifier}: command, verify and outputs must be nonempty.")
        inputs = strings(item.get("inputs", []), "inputs")
        needs = strings(item.get("needs", []), "needs")
        timeout = number(item.get("timeout_seconds", 60), "timeout_seconds")
        cache = item.get("cache", True)
        if not isinstance(cache, bool) or not 0 < timeout <= 3600:
            raise ValueError("cache must be boolean; timeout must be in (0, 3600].")
        for name in inputs:
            inside(root, name)
        for name in outputs:
            path = inside(root, name)
            if path in owners or path in [inside(root, value) for value in inputs]:
                raise ValueError(f"Duplicate or in-place output: {name}")
            owners[path] = identifier
        steps[identifier] = Step(identifier, command, verify, needs, inputs, outputs, timeout, cache)
    ordered: list[Step] = []
    visiting: set[str] = set()
    visited: set[str] = set()
    ancestors: dict[str, set[str]] = {}

    def visit(identifier: str) -> None:
        if identifier in visiting:
            raise ValueError("Dependency cycle detected.")
        if identifier in visited:
            return
        if identifier not in steps:
            raise ValueError(f"Unknown dependency: {identifier}")
        visiting.add(identifier)
        parents: set[str] = set()
        for parent in steps[identifier].needs:
            visit(parent)
            parents.update(ancestors[parent] | {parent})
        ancestors[identifier] = parents
        visiting.remove(identifier)
        visited.add(identifier)
        ordered.append(steps[identifier])

    for identifier in steps:
        visit(identifier)
    for step in ordered:
        for name in step.inputs:
            owner = owners.get(inside(root, name))
            if owner and owner not in ancestors[step.id]:
                raise ValueError(f"{step.id} consumes {name} without depending on {owner}.")
    budget = number(manifest.get("max_seconds", 300), "max_seconds")
    if not 0 < budget <= 86400:
        raise ValueError("max_seconds must be in (0, 86400].")
    return ordered, budget


def fingerprints(root: Path, names: list[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name in names:
        path = inside(root, name)
        if not path.is_file():
            raise ValueError(f"Required file is missing: {name}")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while block := handle.read(1024 * 1024):
                digest.update(block)
        hashes[name] = digest.hexdigest()
    return hashes


def atomic_save(path: Path, value: object) -> None:
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(canonical(value))
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def stop_process(process: subprocess.Popen[bytes]) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait()


def execute(argv: list[str], root: Path, log: Path, timeout: float) -> dict[str, object]:
    started = time.monotonic()
    if timeout <= 0:
        return {"ok": False, "reason": "Workflow time budget exhausted.", "seconds": 0.0}
    command = [sys.executable if part == "{python}" else part for part in argv]
    with log.open("wb") as output:
        process = subprocess.Popen(
            command,
            cwd=root,
            stdout=output,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            shell=False,
            start_new_session=os.name != "nt",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        reason = ""
        try:
            while process.poll() is None:
                if time.monotonic() - started > timeout:
                    reason = "Command exceeded its time budget."
                    stop_process(process)
                    break
                if log.stat().st_size > MAX_LOG:
                    reason = "Command exceeded the 5 MiB log limit."
                    stop_process(process)
                    break
                time.sleep(0.025)
        except BaseException:
            stop_process(process)
            raise
    if log.stat().st_size > MAX_LOG:
        reason = "Command exceeded the 5 MiB log limit."
    with log.open("rb") as output:
        excerpt = output.read(4000).decode("utf-8", errors="replace")
    return {
        "ok": not reason and process.returncode == 0,
        "exit_code": process.returncode,
        "reason": reason or ("Completed." if process.returncode == 0 else "Command failed."),
        "seconds": round(time.monotonic() - started, 4),
        "log": str(log.relative_to(root)),
        "excerpt": excerpt,
    }


def run(manifest: dict[str, object], workspace: Path) -> dict[str, object]:
    root = workspace.resolve(strict=True)
    steps, budget = parse(manifest, root)
    state = root / ".workflowproof"
    if state.is_symlink() or (state.exists() and not state.resolve().is_relative_to(root)):
        raise ValueError("Evidence directory must be local to the workspace.")
    state.mkdir(exist_ok=True)
    lock = state / "run.lock"
    try:
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise ValueError(
            "Workspace is locked. If a run crashed, confirm it stopped before removing run.lock."
        ) from error
    with os.fdopen(descriptor, "w") as handle:
        handle.write(str(os.getpid()))
    try:
        return _run_locked(steps, budget, root, state)
    finally:
        lock.unlink(missing_ok=True)


def _run_locked(steps: list[Step], budget: float, root: Path, state: Path) -> dict[str, object]:
    started = time.monotonic()
    run_id = uuid.uuid4().hex
    run_dir = state / run_id
    run_dir.mkdir()
    cache_path = state / "cache.json"
    try:
        cache = load(cache_path) if cache_path.exists() else {}
    except (ValueError, OSError):
        cache = {}
    results: dict[str, dict[str, object]] = {}
    environment = hashlib.sha256(canonical(dict(os.environ))).hexdigest()
    for step in steps:
        failed_parents = [
            parent for parent in step.needs if results[parent]["status"] not in {"passed", "reused"}
        ]
        if failed_parents:
            results[step.id] = {"status": "skipped", "reason": f"Dependencies failed: {failed_parents}"}
            continue
        if time.monotonic() - started >= budget:
            results[step.id] = {"status": "skipped", "reason": "Workflow time budget exhausted."}
            continue
        try:
            inputs = fingerprints(root, step.inputs)
            parent_evidence = {parent: results[parent]["evidence"] for parent in step.needs}
            signature = hashlib.sha256(
                canonical(
                    {
                        "contract": asdict(step),
                        "inputs": inputs,
                        "parents": parent_evidence,
                        "python": sys.version,
                        "environment": environment,
                        "workspace": str(root),
                    }
                )
            ).hexdigest()
            entry = mapping(cache.get(step.id, {}))
            reusable = False
            if step.cache and entry.get("signature") == signature:
                try:
                    reusable = fingerprints(root, step.outputs) == entry.get("outputs")
                except ValueError:
                    reusable = False
            verification: dict[str, object] = {}
            if reusable:
                verification = execute(
                    step.verify,
                    root,
                    run_dir / f"{step.id}-cache-check.log",
                    min(step.timeout, budget - (time.monotonic() - started)),
                )
                reusable = (
                    verification["ok"] is True
                    and fingerprints(root, step.outputs) == entry.get("outputs")
                    and fingerprints(root, step.inputs) == inputs
                )
            execution: dict[str, object] = {"reason": "Primary command reused from matching evidence."}
            if not reusable:
                execution = execute(
                    step.command,
                    root,
                    run_dir / f"{step.id}-run.log",
                    min(step.timeout, budget - (time.monotonic() - started)),
                )
                if execution["ok"] is not True:
                    results[step.id] = {"status": "failed", "execution": execution}
                    cache.pop(step.id, None)
                    atomic_save(cache_path, cache)
                    continue
                verification = execute(
                    step.verify,
                    root,
                    run_dir / f"{step.id}-verify.log",
                    min(step.timeout, budget - (time.monotonic() - started)),
                )
                if verification["ok"] is not True:
                    results[step.id] = {
                        "status": "failed",
                        "execution": execution,
                        "verification": verification,
                    }
                    cache.pop(step.id, None)
                    atomic_save(cache_path, cache)
                    continue
            outputs = fingerprints(root, step.outputs)
            if fingerprints(root, step.inputs) != inputs:
                raise ValueError("Declared inputs changed while the step ran; evidence is invalid.")
            evidence = hashlib.sha256(canonical({"signature": signature, "outputs": outputs})).hexdigest()
            results[step.id] = {
                "status": "reused" if reusable else "passed",
                "evidence": evidence,
                "inputs": inputs,
                "outputs": outputs,
                "execution": execution,
                "verification": verification,
            }
            cache[step.id] = {"signature": signature, "outputs": outputs, "evidence": evidence}
            atomic_save(cache_path, cache)
        except (ValueError, OSError) as error:
            results[step.id] = {"status": "failed", "reason": str(error)}
            cache.pop(step.id, None)
            atomic_save(cache_path, cache)
    for step in steps:
        result = results[step.id]
        if result["status"] in {"passed", "reused"}:
            try:
                if (
                    fingerprints(root, step.outputs) != result["outputs"]
                    or fingerprints(root, step.inputs) != result["inputs"]
                ):
                    raise ValueError("Files changed after this step was verified.")
            except (ValueError, OSError) as error:
                results[step.id] = {**result, "status": "failed", "reason": str(error)}
                cache.pop(step.id, None)
    atomic_save(cache_path, cache)
    success = all(value["status"] in {"passed", "reused"} for value in results.values())
    receipt = {
        "run_id": run_id,
        "success": success,
        "seconds": round(time.monotonic() - started, 4),
        "steps": results,
        "reused_steps": sum(value["status"] == "reused" for value in results.values()),
        "boundary": "Trusted commands and local evidence. Only declared dependencies are tracked.",
    }
    atomic_save(run_dir / "receipt.json", receipt)
    atomic_save(state / "latest.json", receipt)
    return receipt
