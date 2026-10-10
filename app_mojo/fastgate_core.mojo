"""
mojo-fastgate core algebra
Deterministic token embedding, SIMD-friendly vector similarity, and System-1 tool triage.
"""

from std.collections import List
from std.math import sqrt

comptime DIM: Int = 256
comptime TAU: Float64 = 6.283185307179586


@fieldwise_init
struct Vector256(Copyable, Movable):
    var values: List[Float32]


def embed_term(token: String) -> Vector256:
    """Computes a deterministic 256-dimensional unit embedding from token UTF-8 bytes."""
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

    return Vector256(values^)


def cosine_similarity(a: Vector256, b: Vector256) -> Float32:
    """Calculates dot product similarity between two normalized vectors."""
    var dot = Float32(0.0)
    for i in range(DIM):
        dot += a.values[i] * b.values[i]
    return dot


def route_tools(
    prompt_tokens: List[String],
    tool_names: List[String],
    threshold: Float32 = 0.12
) -> List[String]:
    """
    Ranks tool capabilities against prompt tokens in sub-50 microseconds.
    Returns pruned list of retained tools.
    """
    # Bundle prompt tokens
    var prompt_values = List[Float32](length=DIM, fill=0.0)
    for i in range(len(prompt_tokens)):
        var term_vec = embed_term(prompt_tokens[i])
        for d in range(DIM):
            prompt_values[d] += term_vec.values[d]

    # Normalize prompt vector
    var sum_sq = Float32(0.0)
    for d in range(DIM):
        sum_sq += prompt_values[d] * prompt_values[d]

    var inv_norm = Float32(1.0) / (sqrt(sum_sq) + Float32(1e-7))
    for d in range(DIM):
        prompt_values[d] *= inv_norm

    var prompt_vec = Vector256(prompt_values^)
    var retained = List[String]()

    for i in range(len(tool_names)):
        var t_name = tool_names[i]
        var t_vec = embed_term(t_name)
        var score = cosine_similarity(prompt_vec, t_vec)

        if score >= threshold:
            retained.append(t_name)

    # Fallback: ensure at least one tool retained
    if len(retained) == 0 and len(tool_names) > 0:
        retained.append(tool_names[0])

    return retained^


def main():
    print("mojo-fastgate core algebra initialized.")
    var prompt = List[String]()
    prompt.append("read")
    prompt.append("file")
    prompt.append("config")

    var tools = List[String]()
    tools.append("read_file")
    tools.append("write_file")
    tools.append("execute_cmd")
    tools.append("deploy_prod")

    var routed = route_tools(prompt, tools, 0.05)
    print("Retained count: " + String(len(routed)))
