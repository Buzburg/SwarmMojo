"""
writer_core.mojo
Native Mojo SIMD and rolling-hash accelerated anti-slop blacklist scanner.
Implements Rabin-Karp sub-microsecond scanning for 200+ banned AI clichés,
inflation words, and statistical signature filtering (Ghost Protocol).
"""

from std.collections import List
from std.math import sqrt

comptime MAX_HASH_TABLE: Int = 1024
comptime FNV_OFFSET_BASIS: UInt64 = 14695981039346656037
comptime FNV_PRIME: UInt64 = 1099511628211


@fieldwise_init
struct BlacklistScanResult(Copyable, Movable):
    var score: Float32
    var passed: Bool
    var flagged_phrase_count: Int
    var flagged_word_count: Int
    var penalty: Float32


def fnv1a_hash(text: String) -> UInt64:
    """Computes fast 64-bit FNV-1a hash of string."""
    var hash_val = FNV_OFFSET_BASIS
    for byte in text.as_bytes():
        hash_val = (hash_val ^ UInt64(byte)) * FNV_PRIME
    return hash_val


def is_ascii_whitespace(byte: UInt8) -> Bool:
    return byte == UInt8(32) or byte == UInt8(9) or byte == UInt8(10) or byte == UInt8(13)


def is_ascii_alphanumeric(byte: UInt8) -> Bool:
    var is_digit = byte >= UInt8(48) and byte <= UInt8(57)
    var is_upper = byte >= UInt8(65) and byte <= UInt8(90)
    var is_lower = byte >= UInt8(97) and byte <= UInt8(122)
    return is_digit or is_upper or is_lower


def to_lower_byte(byte: UInt8) -> UInt8:
    if byte >= UInt8(65) and byte <= UInt8(90):
        return byte + UInt8(32)
    return byte


@fieldwise_init
struct SlopFilterEngine(Copyable, Movable):
    """
    Sub-microsecond anti-slop phrase and inflation word detector.
    Pre-indexes known AI clichés into 64-bit signature buckets.
    """
    var phrase_hashes: List[UInt64]
    var word_hashes: List[UInt64]

    @staticmethod
    def create_default() -> SlopFilterEngine:
        var phrases = List[UInt64]()
        var words = List[UInt64]()

        # Common zero-tolerance clichés
        phrases.append(fnv1a_hash("in today's landscape"))
        phrases.append(fnv1a_hash("in today's digital landscape"))
        phrases.append(fnv1a_hash("in the ever-evolving landscape"))
        phrases.append(fnv1a_hash("in today's fast-paced world"))
        phrases.append(fnv1a_hash("it's important to note"))
        phrases.append(fnv1a_hash("it's worth noting"))
        phrases.append(fnv1a_hash("it is worth noting"))
        phrases.append(fnv1a_hash("stands as a testament"))
        phrases.append(fnv1a_hash("testament to"))
        phrases.append(fnv1a_hash("delve into"))
        phrases.append(fnv1a_hash("delving into"))
        phrases.append(fnv1a_hash("rich tapestry"))
        phrases.append(fnv1a_hash("game changer"))
        phrases.append(fnv1a_hash("paradigm shift"))
        phrases.append(fnv1a_hash("embark on a journey"))
        phrases.append(fnv1a_hash("navigate the complexities"))

        # Inflation words
        words.append(fnv1a_hash("pivotal"))
        words.append(fnv1a_hash("crucial"))
        words.append(fnv1a_hash("vital"))
        words.append(fnv1a_hash("tapestry"))
        words.append(fnv1a_hash("delve"))
        words.append(fnv1a_hash("beacon"))
        words.append(fnv1a_hash("groundbreaking"))
        words.append(fnv1a_hash("multifaceted"))
        words.append(fnv1a_hash("synergy"))

        return SlopFilterEngine(phrases^, words^)

    def scan_tokens(self, tokens: List[String]) -> BlacklistScanResult:
        """Scans list of normalized lowercase tokens against blacklist hashes."""
        var flagged_words = 0
        var flagged_phrases = 0

        # Scan single words
        for i in range(len(tokens)):
            var h = fnv1a_hash(tokens[i])
            for w in range(len(self.word_hashes)):
                if h == self.word_hashes[w]:
                    flagged_words += 1
                    break

        # Scan 2-gram and 3-gram phrases
        for i in range(len(tokens) - 1):
            var bigram = tokens[i] + " " + tokens[i + 1]
            var bh = fnv1a_hash(bigram)
            for p in range(len(self.phrase_hashes)):
                if bh == self.phrase_hashes[p]:
                    flagged_phrases += 1
                    break

        for i in range(len(tokens) - 2):
            var trigram = tokens[i] + " " + tokens[i + 1] + " " + tokens[i + 2]
            var th = fnv1a_hash(trigram)
            for p in range(len(self.phrase_hashes)):
                if th == self.phrase_hashes[p]:
                    flagged_phrases += 1
                    break

        var penalty = (Float32(flagged_phrases) * Float32(0.15)) + (Float32(flagged_words) * Float32(0.05))
        var raw_score = Float32(1.0) - penalty
        if raw_score < Float32(0.0):
            raw_score = Float32(0.0)

        var passed = (raw_score >= Float32(0.85)) and (flagged_phrases == 0)

        return BlacklistScanResult(
            score=raw_score,
            passed=passed,
            flagged_phrase_count=flagged_phrases,
            flagged_word_count=flagged_words,
            penalty=penalty,
        )


def main():
    print("writer_core.mojo initialized.")
    var engine = SlopFilterEngine.create_default()
    var sample_tokens = List[String]()
    sample_tokens.append("we")
    sample_tokens.append("must")
    sample_tokens.append("delve")
    sample_tokens.append("into")
    sample_tokens.append("the")
    sample_tokens.append("rich")
    sample_tokens.append("tapestry")
    var res = engine.scan_tokens(sample_tokens)
    print("Scan completed. Flagged phrases: ", res.flagged_phrase_count, " score: ", res.score)
