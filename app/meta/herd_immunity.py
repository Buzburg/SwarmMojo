"""Fleet Herd Immunity Engine for SwarmMojo by Buzburg AI.

Fleet herd immunity architecture by Buzburg AI:
- When any agent in the swarm discovers and resolves an error, it generates an Immunity Signature.
- The immunity signature is broadcast across the peer agent fleet.
- When any peer encounters a matching error signature, it instantly applies the remedy, preventing duplicate failure loops across the fleet.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ImmunitySignature:
    immunity_id: str
    error_type: str
    error_pattern: str       # Substring or regex to match
    root_cause: str
    remedy: str
    prevention_rule: str
    discovered_by: str
    created_at: float = field(default_factory=time.time)
    applications_count: int = 0

    @property
    def antibody_id(self) -> str:
        """Backward-compatible alias for legacy callers."""
        return self.immunity_id

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["antibody_id"] = self.immunity_id
        return d


# Backward-compatible alias
AntibodySignature = ImmunitySignature


class HerdImmunityRegistry:
    """Manages fleet-wide herd immunity memory against recurring errors."""

    def __init__(self, storage_path: Optional[str | Path] = None):
        self.storage_path = Path(storage_path).resolve() if storage_path else None
        self.immunities: Dict[str, ImmunitySignature] = {}
        self._init_default_immunities()

    @property
    def antibodies(self) -> Dict[str, ImmunitySignature]:
        """Backward-compatible property for legacy callers."""
        return self.immunities

    def _init_default_immunities(self) -> None:
        """Seeds common universal failure modes so fleets are born immune."""
        self.register_immunity(
            error_type="ModuleNotFoundError",
            error_pattern="No module named 'fcntl'",
            root_cause="POSIX fcntl is not available on Windows NT environments.",
            remedy="Use conditional import: try: import fcntl except ImportError: fcntl = None.",
            prevention_rule="Always guard platform-specific POSIX APIs with os.name == 'posix'.",
            discovered_by="fleet_core",
        )
        self.register_immunity(
            error_type="PermissionError",
            error_pattern="[WinError 32] The process cannot access the file because it is being used by another process",
            root_cause="SQLite database or file handle remains open on Windows during directory cleanup.",
            remedy="Explicitly call db.close() or connection.close() in finally block before cleanup.",
            prevention_rule="Ensure all Windows file handles and SQLite connections close deterministically.",
            discovered_by="fleet_core",
        )
        self.register_immunity(
            error_type="NotImplementedError",
            error_pattern="dir_fd unavailable",
            root_cause="os.supports_dir_fd is empty on Windows NT.",
            remedy="Fall back to strict canonical path.resolve() boundary checking when dir_fd is unsupported.",
            prevention_rule="Verify os.supports_dir_fd before passing file descriptor directories.",
            discovered_by="fleet_core",
        )

    def register_immunity(
        self,
        error_type: str,
        error_pattern: str,
        root_cause: str,
        remedy: str,
        prevention_rule: str,
        discovered_by: str = "agent",
    ) -> ImmunitySignature:
        """Registers a new immunity signature in the swarm immunity pool."""
        raw_key = f"{error_type}:{error_pattern}:{root_cause}"
        immunity_id = f"ab_{hashlib.sha256(raw_key.encode('utf-8')).hexdigest()[:12]}"

        sig = ImmunitySignature(
            immunity_id=immunity_id,
            error_type=error_type,
            error_pattern=error_pattern,
            root_cause=root_cause,
            remedy=remedy,
            prevention_rule=prevention_rule,
            discovered_by=discovered_by,
        )
        self.immunities[immunity_id] = sig
        return sig

    # Backward-compatible alias
    register_antibody = register_immunity

    def check_immunity(self, error_text: str) -> List[ImmunitySignature]:
        """Scans error text against fleet immunities. Returns matching preventative remedies."""
        matches: List[ImmunitySignature] = []
        for sig in self.immunities.values():
            try:
                if sig.error_pattern in error_text or re.search(re.escape(sig.error_pattern), error_text, re.IGNORECASE):
                    sig.applications_count += 1
                    matches.append(sig)
            except Exception:
                if sig.error_pattern in error_text:
                    sig.applications_count += 1
                    matches.append(sig)
        return matches

    def summary(self) -> Dict[str, Any]:
        return {
            "total_immunities": len(self.immunities),
            "total_antibodies": len(self.immunities),
            "total_applications": sum(sig.applications_count for sig in self.immunities.values()),
            "active_signatures": [sig.to_dict() for sig in self.immunities.values()],
        }


# Backward-compatible alias
AntibodyRegistry = HerdImmunityRegistry
