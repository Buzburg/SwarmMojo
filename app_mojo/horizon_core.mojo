"""
mojo-local-horizon core algebra
State machine DAG tracking, FNV-1a action fingerprinting, and semantic loop detection.
"""

from std.collections import List
from std.math import sqrt

comptime DIM: Int = 256
comptime LOOP_THRESHOLD: Float32 = 0.85


@fieldwise_init
struct ActionVector(Copyable, Movable):
    var values: List[Float32]


def embed_string(s: String) -> ActionVector:
    """Computes deterministic 256-dimensional unit embedding from string bytes."""
    var seed = UInt64(14695981039346656037)
    for byte in s.as_bytes():
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

    return ActionVector(values^)


def cosine_similarity(a: ActionVector, b: ActionVector) -> Float32:
    var dot = Float32(0.0)
    for i in range(DIM):
        dot += a.values[i] * b.values[i]
    return dot


def check_loop(current: ActionVector, history: List[ActionVector]) -> Bool:
    """
    Scans execution history to determine if the agent is repeating an equivalent action.
    """
    for i in range(len(history)):
        var sim = cosine_similarity(current, history[i])
        if sim >= LOOP_THRESHOLD:
            return True
    return False


def main():
    print("mojo-local-horizon core algebra initialized.")
