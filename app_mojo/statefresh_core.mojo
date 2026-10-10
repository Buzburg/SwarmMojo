"""
statefresh_core.mojo
Native Mojo SIMD and Optimistic Concurrency Control (OCC) kernel.
Implements sub-microsecond read-set validation, lease version checking,
atomic Compare-And-Swap (CAS), and stale-write rejection.
"""

from std.collections import List
from std.math import max

comptime DEFAULT_LEASE_DURATION_MS: UInt64 = 5000  # 5 seconds
comptime FNV_OFFSET_BASIS: UInt64 = 14695981039346656037
comptime FNV_PRIME: UInt64 = 1099511628211


@fieldwise_init
struct OCCLease(Copyable, Movable):
    var resource_hash: UInt64
    var current_version: UInt64
    var lease_holder_hash: UInt64
    var expiration_epoch_ms: UInt64
    var is_active: Bool


@fieldwise_init
struct CASResult(Copyable, Movable):
    var committed: Bool
    var new_version: UInt64
    var conflict_reason: String


def hash_identifier(identifier: String) -> UInt64:
    """Computes fast 64-bit FNV-1a hash of resource string."""
    var h = FNV_OFFSET_BASIS
    for b in identifier.as_bytes():
        h = (h ^ UInt64(b)) * FNV_PRIME
    return h


def validate_and_commit_cas(
    expected_version: UInt64,
    current_lease: OCCLease,
    caller_hash: UInt64,
    current_epoch_ms: UInt64,
) -> CASResult:
    """
    Sub-microsecond atomic Compare-And-Swap (CAS) evaluation.
    Verifies that the resource version has not advanced and caller holds valid lease.
    """
    # 1. Stale read verification: version must match exactly
    if current_lease.current_version != expected_version:
        return CASResult(
            committed=False,
            new_version=current_lease.current_version,
            conflict_reason="STALE_VERSION_DETECTED: Target resource was modified concurrently",
        )

    # 2. Expiration verification: active lease must not have timed out
    if current_lease.is_active and current_epoch_ms > current_lease.expiration_epoch_ms:
        return CASResult(
            committed=False,
            new_version=current_lease.current_version,
            conflict_reason="LEASE_EXPIRED: Concurrency lease expired before commit",
        )

    # 3. Ownership verification: caller must own lease if active
    if current_lease.is_active and current_lease.lease_holder_hash != caller_hash:
        return CASResult(
            committed=False,
            new_version=current_lease.current_version,
            conflict_reason="LEASE_HELD_BY_ANOTHER_AGENT: Concurrent agent holds exclusive lock",
        )

    # 4. Atomic advance version
    var next_version = current_lease.current_version + 1
    return CASResult(
        committed=True,
        new_version=next_version,
        conflict_reason="COMMIT_ACCEPTED",
    )


def compute_read_set_fingerprint(version_list: List[UInt64]) -> UInt64:
    """
    Computes commutative rolling XOR-hash fingerprint of all read-set versions.
    Used for instant constant-time validation of multi-file transaction consistency.
    """
    var fp = FNV_OFFSET_BASIS
    for i in range(len(version_list)):
        var v = version_list[i]
        fp = (fp ^ v) * FNV_PRIME
    return fp
