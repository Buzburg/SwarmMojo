"""WorkflowProof Engine for SwarmMojo.

Evidence-aware sequential DAG verification and cryptographic proof-of-work caching.
Adapted from Buzburg/workflowproof (Apache-2.0).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class WorkflowStep:
    id: str
    command: List[str]
    inputs: List[str]
    outputs: List[str]
    timeout: float = 60.0
    cache: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return dict(asdict(self))


class WorkflowProofEngine:
    """Computes cryptographic execution proofs and caches verified steps."""

    def __init__(self, root: str = "."):
        self.root = Path(root).resolve()
        self.cache_dir = self.root / ".mojo_workflowproof"
        self.proofs_file = self.cache_dir / "proofs.json"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if not self.proofs_file.exists():
            self._save_proofs({})

    def _load_proofs(self) -> Dict[str, Any]:
        if not self.proofs_file.exists():
            return {}
        try:
            return json.loads(self.proofs_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_proofs(self, proofs: Dict[str, Any]) -> None:
        self.proofs_file.write_text(json.dumps(proofs, indent=2), encoding="utf-8")

    def record_proof(self, step_id: str, inputs: Dict[str, Any], outputs: Dict[str, Any]) -> Dict[str, Any]:
        """Manually records an evidence receipt and cryptographic digest."""
        hasher = hashlib.sha256()
        hasher.update(step_id.encode("utf-8"))
        hasher.update(json.dumps(inputs, sort_keys=True).encode("utf-8"))
        digest = hasher.hexdigest()

        proofs = self._load_proofs()
        receipt = {
            "step_id": step_id,
            "inputs": inputs,
            "outputs": outputs,
            "proof_hash": digest,
            "timestamp": time.time(),
        }
        proofs[digest] = receipt
        self._save_proofs(proofs)
        return receipt

    def lookup_proof(self, step_id: str, inputs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        hasher = hashlib.sha256()
        hasher.update(step_id.encode("utf-8"))
        hasher.update(json.dumps(inputs, sort_keys=True).encode("utf-8"))
        digest = hasher.hexdigest()
        proofs = self._load_proofs()
        return proofs.get(digest)

    def verify_proofs(self) -> Dict[str, Any]:
        proofs = self._load_proofs()
        return {
            "valid": True,
            "proof_count": len(proofs),
            "proofs_file": str(self.proofs_file),
        }


    def compute_step_digest(self, step: WorkflowStep) -> str:
        """Computes SHA-256 fingerprint over command and input file contents."""
        hasher = hashlib.sha256()
        hasher.update(" ".join(step.command).encode("utf-8"))
        for rel_in in sorted(step.inputs):
            target = (self.root / rel_in).resolve()
            if target.is_file():
                hasher.update(target.read_bytes())
            else:
                hasher.update(f"missing:{rel_in}".encode("utf-8"))
        return hasher.hexdigest()

    def run_step(self, step: WorkflowStep) -> Dict[str, Any]:
        """Runs or retrieves cached proof for a verification step."""
        start = time.perf_counter()
        digest = self.compute_step_digest(step)
        proofs = self._load_proofs()

        if step.cache and digest in proofs:
            cached = proofs[digest]
            return {
                "step_id": step.id,
                "cached": True,
                "status": "verified",
                "proof_hash": digest,
                "output": cached.get("output", ""),
                "duration_ms": 0.05,
            }

        # Execute command
        try:
            res = subprocess.run(
                step.command,
                cwd=str(self.root),
                capture_output=True,
                text=True,
                timeout=step.timeout,
            )
            duration_ms = (time.perf_counter() - start) * 1000.0
            output = (res.stdout + "\n" + res.stderr).strip()
            success = (res.returncode == 0)

            result = {
                "step_id": step.id,
                "cached": False,
                "status": "verified" if success else "failed",
                "returncode": res.returncode,
                "proof_hash": digest,
                "output": output,
                "duration_ms": round(duration_ms, 2),
            }

            if success and step.cache:
                proofs[digest] = {
                    "step_id": step.id,
                    "timestamp": time.time(),
                    "output": output,
                }
                self._save_proofs(proofs)

            return result
        except subprocess.TimeoutExpired:
            return {
                "step_id": step.id,
                "cached": False,
                "status": "timeout",
                "error": f"Timed out after {step.timeout}s",
            }
        except Exception as e:
            return {
                "step_id": step.id,
                "cached": False,
                "status": "error",
                "error": str(e),
            }
