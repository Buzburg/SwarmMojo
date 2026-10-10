"""
assistant_core.mojo
Native Mojo SIMD and signal processing kernel for Personal Assistant.
Implements audio PCM energy-gated Voice Activity Detection (VAD),
barge-in interruption thresholding, and fast preference vector matching.
"""

from std.collections import List
from std.math import sqrt

comptime SILENCE_THRESHOLD_RMS: Float32 = 0.015
comptime BARGE_IN_THRESHOLD_RMS: Float32 = 0.080


@fieldwise_init
struct AudioEnergyMetrics(Copyable, Movable):
    var rms_energy: Float32
    var is_speech_active: Bool
    var is_barge_in_triggered: Bool


def calculate_pcm16_energy(samples: List[Float32]) -> AudioEnergyMetrics:
    """
    Computes RMS (Root Mean Square) energy of normalized PCM audio samples [-1.0, 1.0].
    RMS = sqrt( (1/N) * sum(x_i^2) )
    """
    var n = len(samples)
    if n == 0:
        return AudioEnergyMetrics(
            rms_energy=0.0,
            is_speech_active=False,
            is_barge_in_triggered=False,
        )

    var sum_sq = Float32(0.0)
    for i in range(n):
        var s = samples[i]
        sum_sq += s * s

    var mean_sq = sum_sq / Float32(n)
    var rms = sqrt(mean_sq)

    var active = rms >= SILENCE_THRESHOLD_RMS
    var barge_in = rms >= BARGE_IN_THRESHOLD_RMS

    return AudioEnergyMetrics(
        rms_energy=rms,
        is_speech_active=active,
        is_barge_in_triggered=barge_in,
    )


def match_preference_score(query_vec: List[Float32], pref_vec: List[Float32], dim: Int = 32) -> Float32:
    """Computes dot product similarity between query and personal preference vector."""
    var dot = Float32(0.0)
    var limit = dim
    if len(query_vec) < limit:
        limit = len(query_vec)
    if len(pref_vec) < limit:
        limit = len(pref_vec)

    for i in range(limit):
        dot += query_vec[i] * pref_vec[i]

    return dot


def main():
    print("assistant_core.mojo initialized.")
    var dummy_samples = List[Float32]()
    for _ in range(160):  # 10ms at 16kHz
        dummy_samples.append(0.05)
    var m = calculate_pcm16_energy(dummy_samples)
    print("VAD RMS: ", m.rms_energy, " Speech active: ", m.is_speech_active)
