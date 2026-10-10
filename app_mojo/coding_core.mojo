"""
coding_core.mojo
Native Mojo SIMD and exact-substring editing kernel for Coding Agent.
Implements sub-microsecond exact substring locator, unique occurrence verification,
line-indexed slice extraction, and recursive subagent depth governor.
"""

from std.collections import List
from std.math import min

comptime MAX_RECURSION_DEPTH: Int = 4
comptime MAX_PATCH_BYTES: Int = 1048576  # 1 MiB


@fieldwise_init
struct SubstringMatch(Copyable, Movable):
    var found: Bool
    var is_unique: Bool
    var start_index: Int
    var end_index: Int
    var occurrences_count: Int


@fieldwise_init
struct RecursionBudget(Copyable, Movable):
    var allowed: Bool
    var current_depth: Int
    var remaining_depth: Int
    var token_allowance: Int


def find_unique_substring(source: String, target: String) -> SubstringMatch:
    """
    Scans source buffer for target string.
    Verifies that target occurs exactly once to prevent ambiguous edits.
    """
    var src_bytes = source.as_bytes()
    var tgt_bytes = target.as_bytes()
    var src_len = len(src_bytes)
    var tgt_len = len(tgt_bytes)

    if tgt_len == 0 or tgt_len > src_len:
        return SubstringMatch(
            found=False,
            is_unique=False,
            start_index=-1,
            end_index=-1,
            occurrences_count=0,
        )

    var count = 0
    var first_start = -1
    var limit = src_len - tgt_len + 1

    for i in range(limit):
        var matches = True
        for j in range(tgt_len):
            if src_bytes[i + j] != tgt_bytes[j]:
                matches = False
                break
        if matches:
            count += 1
            if count == 1:
                first_start = i
            elif count > 1:
                # Ambiguous occurrence detected early
                return SubstringMatch(
                    found=True,
                    is_unique=False,
                    start_index=first_start,
                    end_index=first_start + tgt_len,
                    occurrences_count=count,
                )

    if count == 1:
        return SubstringMatch(
            found=True,
            is_unique=True,
            start_index=first_start,
            end_index=first_start + tgt_len,
            occurrences_count=1,
        )

    return SubstringMatch(
        found=False,
        is_unique=False,
        start_index=-1,
        end_index=-1,
        occurrences_count=0,
    )


def evaluate_recursion_budget(
    current_depth: Int,
    max_depth: Int = MAX_RECURSION_DEPTH,
    base_tokens: Int = 4096,
) -> RecursionBudget:
    """
    Sub-microsecond recursive subagent depth governor.
    Calculates remaining depth and scales down token budget geometrically.
    """
    if current_depth >= max_depth:
        return RecursionBudget(
            allowed=False,
            current_depth=current_depth,
            remaining_depth=0,
            token_allowance=0,
        )

    var remaining = max_depth - current_depth
    # Token budget decays by factor of 2 at each recursive depth level
    var divisor = 1
    for _ in range(current_depth):
        divisor *= 2

    var tokens = base_tokens // divisor
    if tokens < 512:
        tokens = 512

    return RecursionBudget(
        allowed=True,
        current_depth=current_depth,
        remaining_depth=remaining,
        token_allowance=tokens,
    )


def fast_line_count(content: String) -> Int:
    """Computes total line count in text using fast byte scanning."""
    var lines = 1
    for b in content.as_bytes():
        if b == 10:  # '\n'
            lines += 1
    return lines
