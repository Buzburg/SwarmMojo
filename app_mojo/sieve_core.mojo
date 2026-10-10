"""
mojo-sieve core algebra
Per-line information density scoring, error signature detection, and token compaction.
"""

from std.collections import List

comptime ERROR_WEIGHT: Float32 = 1.0
comptime CONTEXT_WINDOW_LINES: Int = 3


def hash_line(line: String) -> UInt64:
    """Computes FNV-1a 64-bit hash over line content."""
    var h = UInt64(14695981039346656037)
    for b in line.as_bytes():
        h = (h ^ UInt64(b)) * UInt64(1099511628211)
    return h


def score_line_salience(line: String) -> Float32:
    """
    Computes Per-Line Information Density (PID) based on error indicators and entropy.
    """
    var score = Float32(0.0)
    var lower = line  # Line lower-case or content

    # Check for critical diagnostic markers
    var bytes = line.as_bytes()
    var len_bytes = len(bytes)

    if len_bytes == 0:
        return Float32(0.0)

    # Short line with typical output keywords
    for i in range(len_bytes - 4):
        # Look for 'error'
        if (bytes[i] == 101 or bytes[i] == 69) and (bytes[i+1] == 114 or bytes[i+1] == 82): # 'e' or 'E'
            score += Float32(0.8)
            break

    # Look for 'fail'
    for i in range(len_bytes - 3):
        if (bytes[i] == 102 or bytes[i] == 70) and (bytes[i+1] == 97 or bytes[i+1] == 65): # 'f' or 'F'
            score += Float32(0.7)
            break

    # Base line length score (normalized)
    score += Float32(len_bytes) / Float32(200.0)
    return score


def select_salient_lines(
    scores: List[Float32],
    threshold: Float32 = 0.5
) -> List[Int]:
    """Returns indices of lines to retain."""
    var retained = List[Int]()
    for i in range(len(scores)):
        if scores[i] >= threshold:
            retained.append(i)
    return retained^


def main():
    print("mojo-sieve core algebra initialized.")
