"""
mojo-symdex core algebra
In-memory code symbol vector indexing, call graph adjacency, and fast symbol retrieval.
"""

from std.collections import List
from std.math import sqrt

comptime DIM: Int = 256


@fieldwise_init
struct SymbolVector(Copyable, Movable):
    var symbol_name: String
    var file_path: String
    var line_number: Int
    var embedding: List[Float32]


def embed_symbol(name: String) -> List[Float32]:
    """Generates 256-dimensional unit embedding from symbol name bytes."""
    var seed = UInt64(14695981039346656037)
    for byte in name.as_bytes():
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


def dot_similarity(a: List[Float32], b: List[Float32]) -> Float32:
    var dot = Float32(0.0)
    for i in range(DIM):
        dot += a[i] * b[i]
    return dot


def main():
    print("mojo-symdex core algebra initialized.")
