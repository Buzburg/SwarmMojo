"""
prose_metric.mojo
Native Mojo SIMD and statistical calculator for prose rhythm, sentence variance,
lexical burstiness, and token entropy.
Detects uniform AI cadences and provides quantitative human authenticity scores.
"""

from std.collections import List
from std.math import sqrt, log2

@fieldwise_init
struct RhythmMetrics(Copyable, Movable):
    var sentence_count: Int
    var mean_length: Float32
    var variance: Float32
    var std_dev: Float32
    var is_uniform_cadence: Bool  # True if std_dev < 3.0 and sentence_count >= 3


@fieldwise_init
struct LexicalMetrics(Copyable, Movable):
    var total_tokens: Int
    var unique_tokens: Int
    var type_token_ratio: Float32  # TTR = unique / total
    var entropy: Float32           # Shannon entropy H(X) in bits


def calculate_rhythm_metrics(sentence_lengths: List[Int]) -> RhythmMetrics:
    """Calculates mean, variance, and standard deviation of sentence lengths."""
    var n = len(sentence_lengths)
    if n == 0:
        return RhythmMetrics(
            sentence_count=0,
            mean_length=0.0,
            variance=0.0,
            std_dev=0.0,
            is_uniform_cadence=False,
        )

    var sum_len = Float32(0.0)
    for i in range(n):
        sum_len += Float32(sentence_lengths[i])

    var mean = sum_len / Float32(n)

    var var_sum = Float32(0.0)
    for i in range(n):
        var diff = Float32(sentence_lengths[i]) - mean
        var_sum += diff * diff

    var variance = var_sum / Float32(n)
    var std_dev = sqrt(variance)

    var uniform = (std_dev < Float32(3.0)) and (n >= 3)

    return RhythmMetrics(
        sentence_count=n,
        mean_length=mean,
        variance=variance,
        std_dev=std_dev,
        is_uniform_cadence=uniform,
    )


def calculate_token_entropy(token_counts: List[Int], total_tokens: Int) -> Float32:
    """
    Calculates Shannon entropy: H(X) = -sum(p_i * log2(p_i))
    Higher entropy indicates higher informational density and natural burstiness.
    """
    if total_tokens <= 0 or len(token_counts) == 0:
        return Float32(0.0)

    var entropy = Float32(0.0)
    var total_f = Float32(total_tokens)

    for i in range(len(token_counts)):
        var count = token_counts[i]
        if count > 0:
            var p = Float32(count) / total_f
            # Mojo log2 on Float32
            var log_p = log2(p)
            entropy -= p * log_p

    return entropy


def evaluate_lexical_diversity(unique_count: Int, total_count: Int) -> Float32:
    """Calculates Type-Token Ratio (TTR) with boundary checks."""
    if total_count <= 0:
        return Float32(0.0)
    var ttr = Float32(unique_count) / Float32(total_count)
    if ttr > Float32(1.0):
        ttr = Float32(1.0)
    return ttr


def main():
    print("prose_metric.mojo initialized.")
    var sample_lens = List[Int]()
    sample_lens.append(5)
    sample_lens.append(18)
    sample_lens.append(3)
    sample_lens.append(24)
    sample_lens.append(7)
    var m = calculate_rhythm_metrics(sample_lens)
    print("Sentence count: ", m.sentence_count, " Mean: ", m.mean_length, " StdDev: ", m.std_dev)
