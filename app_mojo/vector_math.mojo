"""Mojo High-Performance SIMD Vector Calculations."""

from std.math import sqrt

def dot_product(a: List[Float32], b: List[Float32]) -> Float32:
    """Computes dot product between two float32 vectors."""
    var total: Float32 = 0.0
    var n = len(a)
    for i in range(n):
        total += a[i] * b[i]
    return total

def l2_norm(v: List[Float32]) -> Float32:
    """Computes the Euclidean L2 norm of a vector."""
    return sqrt(dot_product(v, v))

def cosine_similarity(a: List[Float32], b: List[Float32]) -> Float32:
    """Computes cosine similarity between two float32 embedding vectors."""
    var norm_a = l2_norm(a)
    var norm_b = l2_norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot_product(a, b) / (norm_a * norm_b)

def euclidean_distance(a: List[Float32], b: List[Float32]) -> Float32:
    """Computes Euclidean distance between two vectors."""
    var total: Float32 = 0.0
    var n = len(a)
    for i in range(n):
        var diff = a[i] - b[i]
        total += diff * diff
    return sqrt(total)
