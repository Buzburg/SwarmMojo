"""Original phase-vector algebra. Encoding v1 is intentionally not upstream compatible."""

from std.collections import List
from std.math import atan2, cos, sin

comptime DIM = 512
comptime TAU = 6.283185307179586


@fieldwise_init
struct Phases(Copyable, Movable):
    var values: List[Float64]


def atom(token: String) -> Phases:
    # Full UTF-8 token, not a truncated prefix. Fixed-width arithmetic wraps.
    var seed = UInt64(14695981039346656037)
    for byte in token.as_bytes():
        seed = (seed ^ UInt64(byte)) * UInt64(1099511628211)
    var values = List[Float64](capacity=DIM)
    for _ in range(DIM):
        seed += UInt64(0x9E3779B97F4A7C15)
        var mixed = seed
        mixed = (mixed ^ (mixed >> 30)) * UInt64(0xBF58476D1CE4E5B9)
        mixed = (mixed ^ (mixed >> 27)) * UInt64(0x94D049BB133111EB)
        mixed = mixed ^ (mixed >> 31)
        values.append(Float64(mixed >> 11) * (TAU / 9007199254740992.0))
    return Phases(values^)


def bind(left: Phases, right: Phases) -> Phases:
    var values = List[Float64](capacity=DIM)
    for i in range(DIM):
        values.append(left.values[i] + right.values[i])
    return Phases(values^)


def unbind(bound: Phases, key: Phases) -> Phases:
    var values = List[Float64](capacity=DIM)
    for i in range(DIM):
        values.append(bound.values[i] - key.values[i])
    return Phases(values^)


def encode(tokens: List[String]) -> Phases:
    var real = List[Float64](length=DIM, fill=0.0)
    var imag = List[Float64](length=DIM, fill=0.0)
    for token in tokens:
        var vector = atom(token)
        for i in range(DIM):
            real[i] += cos(vector.values[i])
            imag[i] += sin(vector.values[i])
    var values = List[Float64](capacity=DIM)
    for i in range(DIM):
        values.append(atan2(imag[i], real[i]))
    return Phases(values^)


def similarity(left: Phases, right: Phases) -> Float64:
    var total = Float64(0)
    for i in range(DIM):
        total += cos(left.values[i] - right.values[i])
    return max(-1.0, min(1.0, total / DIM))


def hybrid_score(lexical: Float64, holographic: Float64) -> Float64:
    return 0.7 * lexical + 0.3 * max(0.0, holographic)
