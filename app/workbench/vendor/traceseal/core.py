"""A single-writer hash chain with separately authenticated final checkpoints."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

from ._support import canonical, integer, mapping, text

ZERO = "0" * 64
MAX_LINE = 1_048_576


@dataclass(frozen=True)
class Verification:
    valid: bool
    events: int
    reason: str

    def to_dict(self) -> dict[str, object]:
        return dict(asdict(self))


def keygen(path: Path) -> None:
    """Create a secret without overwriting an existing key. Configure Windows ACLs separately."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(secrets.token_bytes(32))


def validate_key(key: bytes) -> None:
    if len(key) < 32:
        raise ValueError("Use a secret key of at least 32 random bytes.")


def seal(events: Iterable[dict[str, object]], log: Path, checkpoint: Path, key: bytes) -> dict[str, object]:
    """Create a new log and checkpoint. Stream events; never overwrite a previous receipt."""
    validate_key(key)
    if log.resolve() == checkpoint.resolve():
        raise ValueError("Log and checkpoint must be separate paths.")
    if checkpoint.exists():
        raise FileExistsError(checkpoint)
    run_id = str(uuid.uuid4())
    previous = ZERO
    count = 0
    with log.open("x", encoding="utf-8", newline="\n") as handle:
        for count, event in enumerate(events, 1):
            body = {"run_id": run_id, "sequence": count, "previous": previous, "event": mapping(event)}
            previous = hashlib.sha256(canonical(body)).hexdigest()
            encoded = canonical({**body, "hash": previous})
            if len(encoded) + 1 > MAX_LINE:
                raise ValueError("Event exceeds the 1 MiB record limit.")
            handle.write(encoded.decode() + "\n")
            handle.flush()
        os.fsync(handle.fileno())
    body = {"format": 1, "run_id": run_id, "events": count, "head": previous}
    receipt = {**body, "authentication": hmac.new(key, canonical(body), hashlib.sha256).hexdigest()}
    with checkpoint.open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    return receipt


def verify(log: Path, checkpoint: Path, key: bytes) -> Verification:
    validate_key(key)
    count = 0
    try:
        if checkpoint.stat().st_size > 8192:
            return Verification(False, 0, "Checkpoint exceeds size limit.")
        receipt = mapping(json.loads(checkpoint.read_text(encoding="utf-8")))
        if set(receipt) != {"format", "run_id", "events", "head", "authentication"} or receipt["format"] != 1:
            return Verification(False, 0, "Unsupported checkpoint format.")
        authentication = text(receipt.pop("authentication"), "authentication")
        expected = hmac.new(key, canonical(receipt), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(authentication, expected):
            return Verification(False, 0, "Checkpoint authentication failed.")
        total = integer(receipt["events"], "events")
        run_id = text(receipt["run_id"], "run_id")
        previous = ZERO
        with log.open("rb") as handle:
            while line := handle.readline(MAX_LINE + 1):
                if len(line) > MAX_LINE:
                    return Verification(False, count, "Record exceeds size limit.")
                count += 1
                entry = mapping(json.loads(line))
                if set(entry) != {"run_id", "sequence", "previous", "event", "hash"}:
                    return Verification(False, count, f"Unexpected fields at event {count}.")
                digest = text(entry.pop("hash"), "hash")
                if (
                    entry["run_id"] != run_id
                    or integer(entry["sequence"], "sequence") != count
                    or entry["previous"] != previous
                ):
                    return Verification(False, count, f"Chain/order mismatch at event {count}.")
                mapping(entry["event"], "event")
                expected_digest = hashlib.sha256(canonical(entry)).hexdigest()
                if not hmac.compare_digest(digest, expected_digest):
                    return Verification(False, count, f"Content changed at event {count}.")
                previous = digest
        if count != total or previous != receipt["head"]:
            return Verification(
                False, count, "Final checkpoint mismatch: missing, added, or replaced events."
            )
        return Verification(True, count, "Recorded events match the authenticated checkpoint.")
    except (ValueError, OSError, KeyError, UnicodeError, TypeError) as error:
        return Verification(False, count, f"Invalid or unreadable evidence: {error}")
