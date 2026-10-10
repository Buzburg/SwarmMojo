"""
mojo-compact-kv core algebra
Structured scratchpad consolidation, phase-vector fact encoding, and KV cache bounds.
"""

from std.collections import List
from std.math import sqrt

comptime DIM: Int = 256
comptime MAX_FACTS: Int = 16


@fieldwise_init
struct FactVector(Copyable, Movable):
    var text: String
    var vector: List[Float32]


def embed_fact(text: String) -> List[Float32]:
    """Generates 256-dimensional unit embedding from fact bytes."""
    var seed = UInt64(14695981039346656037)
    for byte in text.as_bytes():
        seed = (seed ^ UInt64(byte)) * UInt64(1099511628211)

    var values = List[Float32](capacity=DIM)
    var sum_sq = Float32(0.0)

    for _ in range(DIM):
        seed += UInt64(0x9E3779B97F4A7C15)
        var mixed = seed
        mixed = (mixed ^ (mixed >> 30)) * UInt64(0xBF58476D1CE4E5B9)
        mixed = (mixed ^ (mixed >> 27)) * UInt64(0x94D049BB133111EB)
        mixed = mixed ^ (mixed >> 31)

        var val = Float32(Float64(Int64(mixed % 2000000) - 1000000) / 1000000.0)
        values.append(val)
        sum_sq += val * val

    var inv_norm = Float32(1.0) / sqrt(sum_sq)
    for i in range(DIM):
        values[i] *= inv_norm

    return values^


def deduplicate_fact(new_fact_vec: List[Float32], existing_facts: List[FactVector], threshold: Float32 = 0.8) -> Bool:
    """Returns True if the new fact is already represented in working memory."""
    for i in range(len(existing_facts)):
        var dot = Float32(0.0)
        for d in range(DIM):
            dot += new_fact_vec[d] * existing_facts[i].vector[d]
        if dot >= threshold:
            return True
    return False


def main():
    print("mojo-compact-kv core algebra initialized.")
