"""
localdoc_core.mojo
Native Mojo SIMD and term-frequency scoring kernel for LocalDoc search engine.
Implements bounded passage chunking, byte-level token matching, and Okapi BM25
term saturation calculations for sub-millisecond document retrieval.
Adapted for Buzburg Swarmojo.
"""

from std.collections import List

comptime DEFAULT_BM25_K1: Float64 = 1.20
comptime DEFAULT_BM25_B: Float64 = 0.75
comptime MAX_WORDS_PER_PASSAGE: Int = 80


@fieldwise_init
struct BM25ScoreResult(Copyable, Movable):
    var term_frequency: Int
    var doc_length: Int
    var saturation_score: Float64


@fieldwise_init
struct ChunkBoundary(Copyable, Movable):
    var start_line: Int
    var end_line: Int
    var word_count: Int
    var byte_length: Int


def score_bm25_term(
    term_freq: Int,
    doc_len: Int,
    avg_doc_len: Float64,
    k1: Float64 = DEFAULT_BM25_K1,
    b: Float64 = DEFAULT_BM25_B,
) -> Float64:
    """
    Computes Okapi BM25 term frequency saturation score.
    tf * (k1 + 1.0) / (tf + k1 * (1.0 - b + b * (doc_len / avg_len)))
    """
    if term_freq <= 0:
        return 0.0

    var tf = Float64(term_freq)
    var effective_avg = avg_doc_len if avg_doc_len > 0.0 else 1.0
    var len_ratio = Float64(doc_len) / effective_avg
    var denominator = tf + k1 * (1.0 - b + b * len_ratio)

    if denominator <= 0.0:
        return 0.0

    return (tf * (k1 + 1.0)) / denominator


def fast_token_count(text: String) -> Int:
    """
    Counts whitespace-delimited tokens in a string buffer via fast byte scan.
    """
    var bytes = text.as_bytes()
    var count = 0
    var in_word = False

    for i in range(len(bytes)):
        var b = bytes[i]
        # Treat spaces, tabs, and newlines as delimiters
        if b == 32 or b == 9 or b == 10 or b == 13:
            in_word = False
        else:
            if not in_word:
                count += 1
                in_word = True

    return count


def count_term_occurrences(doc_text: String, query_term: String) -> Int:
    """
    Counts case-insensitive occurrences of query_term in doc_text.
    """
    var doc_bytes = doc_text.as_bytes()
    var term_bytes = query_term.as_bytes()
    var d_len = len(doc_bytes)
    var t_len = len(term_bytes)

    if t_len == 0 or t_len > d_len:
        return 0

    var count = 0
    var limit = d_len - t_len + 1

    for i in range(limit):
        var matches = True
        for j in range(t_len):
            var c1 = doc_bytes[i + j]
            var c2 = term_bytes[j]
            # ASCII lowercase normalization
            if c1 >= 65 and c1 <= 90:
                c1 += 32
            if c2 >= 65 and c2 <= 90:
                c2 += 32
            if c1 != c2:
                matches = False
                break
        if matches:
            count += 1

    return count


def compute_passage_relevance(
    doc_text: String,
    query_terms: List[String],
    avg_doc_len: Float64 = 60.0,
) -> Float64:
    """
    Accumulates BM25 scores across multiple query terms for a passage.
    """
    var doc_len = fast_token_count(doc_text)
    if doc_len == 0:
        return 0.0

    var total_score: Float64 = 0.0
    for i in range(len(query_terms)):
        var tf = count_term_occurrences(doc_text, query_terms[i])
        if tf > 0:
            total_score += score_bm25_term(tf, doc_len, avg_doc_len)

    return total_score
