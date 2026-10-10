"""
mojo-agent-rewind core algebra
Fast FNV-1a rolling file hashing, state vector fingerprinting, and microsecond delta evaluation.
"""

from std.collections import List

comptime FINGERPRINT_SIZE: Int = 8


@fieldwise_init
struct StateFingerprint(Copyable, Movable):
    var lanes: List[UInt64]


def hash_bytes(data: String) -> UInt64:
    """Computes fast FNV-1a 64-bit hash over raw data bytes."""
    var h = UInt64(14695981039346656037)
    for b in data.as_bytes():
        h = (h ^ UInt64(b)) * UInt64(1099511628211)
    return h


def compute_tree_fingerprint(file_hashes: List[UInt64]) -> StateFingerprint:
    """Combines all file hashes into a compact 8-lane state fingerprint vector."""
    var lanes = List[UInt64](length=FINGERPRINT_SIZE, fill=0)

    for i in range(len(file_hashes)):
        var lane_idx = i % FINGERPRINT_SIZE
        var h = file_hashes[i]
        lanes[lane_idx] = (lanes[lane_idx] ^ h) + UInt64(0x9E3779B97F4A7C15)

    return StateFingerprint(lanes^)


def compare_fingerprints(a: StateFingerprint, b: StateFingerprint) -> Bool:
    """Returns True if two state fingerprints match identically."""
    for i in range(FINGERPRINT_SIZE):
        if a.lanes[i] != b.lanes[i]:
            return False
    return True


def main():
    print("mojo-agent-rewind core algebra initialized.")
