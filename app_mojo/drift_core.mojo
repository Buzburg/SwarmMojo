"""
mojo-drift core algebra
Real-time 256-dimensional phase-space trajectory tracking and angular drift calculation.
"""

from std.collections import List
from std.math import sqrt, acos

comptime DIM: Int = 256
comptime RAD_TO_DEG: Float32 = 57.295779513


@fieldwise_init
struct TrajectoryVector(Copyable, Movable):
    var values: List[Float32]


def embed_token(token: String) -> TrajectoryVector:
    """Computes deterministic 256-dimensional unit embedding from token UTF-8 bytes."""
    var seed = UInt64(14695981039346656037)
    for byte in token.as_bytes():
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

    return TrajectoryVector(values^)


def bundle_text(tokens: List[String]) -> TrajectoryVector:
    """Bundles tokens into a normalized trajectory vector."""
    var values = List[Float32](length=DIM, fill=0.0)
    for i in range(len(tokens)):
        var t_vec = embed_token(tokens[i])
        for d in range(DIM):
            values[d] += t_vec.values[d]

    var sum_sq = Float32(0.0)
    for d in range(DIM):
        sum_sq += values[d] * values[d]

    var inv_norm = Float32(1.0) / (sqrt(sum_sq) + Float32(1e-7))
    for d in range(DIM):
        values[d] *= inv_norm

    return TrajectoryVector(values^)


def calculate_angular_drift(goal: TrajectoryVector, action: TrajectoryVector) -> Float32:
    """
    Computes angular drift in degrees [0.0, 180.0].
    θ = acos(clamp(dot_product, -1.0, 1.0)) * (180 / π)
    """
    var dot = Float32(0.0)
    for i in range(DIM):
        dot += goal.values[i] * action.values[i]

    # Clamp for floating-point safety
    if dot > Float32(1.0):
        dot = Float32(1.0)
    elif dot < Float32(-1.0):
        dot = Float32(-1.0)

    # Invert so higher dot product = lower angle
    var rad = acos(dot)
    return rad * RAD_TO_DEG


def main():
    print("mojo-drift core algebra initialized.")
