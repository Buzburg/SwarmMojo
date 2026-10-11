"""
dedup_core.mojo
Native Mojo execution deduplication and cache eviction kernel for Swarmojo by Buzburg AI.
Provides sub-microsecond command key hashing, TTL epoch validation,
and in-memory entry eviction checks.
"""

from std.collections import List

comptime FNV_OFFSET_BASIS_64: UInt64 = 14695981039346656037
comptime FNV_PRIME_64: UInt64 = 1099511628211


@fieldwise_init
struct CacheValidationResult(Copyable, Movable):
    var is_hit: Bool
    var is_expired: Bool
    var age_seconds: Float64
    var remaining_ttl_seconds: Float64


def hash_command_key(tenant_id: String, cwd: String, command: String) -> UInt64:
    """Computes deterministic 64-bit hash for command execution cache keys."""
    var h: UInt64 = FNV_OFFSET_BASIS_64

    var tenant_bytes = tenant_id.as_bytes()
    for i in range(len(tenant_bytes)):
        h = h ^ UInt64(tenant_bytes[i])
        h = h * FNV_PRIME_64

    h = h ^ UInt64(58)  # ':'
    h = h * FNV_PRIME_64

    var cwd_bytes = cwd.as_bytes()
    for i in range(len(cwd_bytes)):
        h = h ^ UInt64(cwd_bytes[i])
        h = h * FNV_PRIME_64

    h = h ^ UInt64(58)  # ':'
    h = h * FNV_PRIME_64

    var cmd_bytes = command.as_bytes()
    for i in range(len(cmd_bytes)):
        h = h ^ UInt64(cmd_bytes[i])
        h = h * FNV_PRIME_64

    return h


def is_cache_entry_expired(current_time: Float64, executed_at: Float64, ttl_seconds: Float64) -> CacheValidationResult:
    """Calculates age and expiry status against given timestamp and TTL."""
    var age = current_time - executed_at
    if age < 0.0:
        age = 0.0
    var expired = age > ttl_seconds
    var remaining = ttl_seconds - age
    if remaining < 0.0:
        remaining = 0.0

    return CacheValidationResult(
        is_hit=not expired,
        is_expired=expired,
        age_seconds=age,
        remaining_ttl_seconds=remaining,
    )


def main():
    print("dedup_core.mojo initialized.")
    var k = hash_command_key("default", "/workspace", "git status")
    print("Command key hash:", k)
