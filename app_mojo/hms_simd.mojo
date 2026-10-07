"""Mojo-HMS: High-Performance SIMD Vector Symbolic Architecture (VSA) Kernel.

Implements 16,384-bit Binary Spatter Code (BSC) for Holographic Memory System.
Ported from Swarmojo/repo_stapler/hms_simd.mojo and adapted for ROMS Mojo runtime:
- 256 x UInt64 words = 16,384 bits per Hypervector
- Bitwise XOR binding (self-inverse: (A ^ B) ^ B = A)
- Cyclic bit permutation for role-filler ordering (Subject, Relation, Object)
- Bipolar cosine similarity and Hopfield associative memory cleanup
"""

alias D = 16384
alias WORDS = 256  # 16384 // 64


struct Hypervector(Movable, Copyable):
    """16,384-bit binary hypervector for Holographic Memory."""
    var words: List[UInt64]

    def __init__(out self):
        self.words = List[UInt64](capacity=WORDS)
        for _ in range(WORDS):
            self.words.append(0)

    def __copyinit__(out self, other: Self):
        self.words = List[UInt64](capacity=WORDS)
        for i in range(len(other.words)):
            self.words.append(other.words[i])

    def __moveinit__(out self, mut other: Self):
        self.words = other.words^

    def set_word(mut self, idx: Int, val: UInt64):
        if idx >= 0 and idx < WORDS:
            self.words[idx] = val

    def get_word(self, idx: Int) -> UInt64:
        if idx >= 0 and idx < WORDS:
            return self.words[idx]
        return 0

    def bind(self, other: Hypervector) -> Hypervector:
        """XOR Binding (A ^ B): Maps two hypervectors to an orthogonal composite vector.
        Self-inverse property: (A ^ B) ^ B = A.
        """
        var result = Hypervector()
        for i in range(WORDS):
            result.words[i] = self.words[i] ^ other.words[i]
        return result^

    def hamming_distance(self, other: Hypervector) -> Int:
        """Normalized bitwise Hamming distance across 16,384 bits."""
        var total_diff: Int = 0
        for i in range(WORDS):
            var diff = self.words[i] ^ other.words[i]
            # Kernighan's bit counting algorithm (1 iteration per set bit)
            while diff > 0:
                diff = diff & (diff - 1)
                total_diff += 1
        return total_diff

    def cosine_similarity(self, other: Hypervector) -> Float32:
        """Bipolar cosine similarity equivalent for Binary Spatter Code:
        cos(theta) = 1.0 - 2.0 * (HammingDistance / D).
        """
        var dist = self.hamming_distance(other)
        return 1.0 - (2.0 * Float32(dist) / Float32(D))

    def permute(self, shift: Int = 1) -> Hypervector:
        """Cyclic word/bit permutation for role-filler binding (e.g. Subject vs Relation vs Object)."""
        var result = Hypervector()
        var word_shift = (shift // 64) % WORDS
        var bit_shift = UInt64(shift % 64)

        for i in range(WORDS):
            var src_idx = (i + WORDS - word_shift) % WORDS
            var next_idx = (src_idx + 1) % WORDS
            var low_bits = self.words[src_idx] << bit_shift
            var high_bits: UInt64 = 0
            if bit_shift > 0:
                high_bits = self.words[next_idx] >> (UInt64(64) - bit_shift)
            result.words[i] = low_bits | high_bits
        return result^


def deterministic_hypervector(seed_str: String) -> Hypervector:
    """Generates a deterministic pseudo-orthogonal 16,384-bit hypervector from a string seed
    using SplitMix64 hashing so that unrelated symbols have ~8,192 Hamming distance.
    """
    var hv = Hypervector()
    var state: UInt64 = 0x9E3779B97F4A7C15
    var bytes = seed_str.as_bytes()
    for i in range(len(bytes)):
        state = (state ^ UInt64(bytes[i])) * 0xBF58476D1CE4E5B9
        state = state ^ (state >> 27)

    for w in range(WORDS):
        state += 0x9E3779B97F4A7C15 + UInt64(w)
        var z = state
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9
        z = (z ^ (z >> 27)) * 0x94D049BB133111EB
        z = z ^ (z >> 31)
        hv.set_word(w, z)
    return hv^


struct HolographicMemoryBank(Movable, Copyable):
    """Associative memory bank with Hopfield cleanup for 16,384-bit hypervectors."""
    var keys: List[String]
    var vectors: List[Hypervector]
    var threshold: Float32

    def __init__(out self, cleanup_threshold: Float32 = 0.15):
        self.keys = List[String]()
        self.vectors = List[Hypervector]()
        self.threshold = cleanup_threshold

    def __copyinit__(out self, other: Self):
        self.keys = List[String]()
        self.vectors = List[Hypervector]()
        self.threshold = other.threshold
        for i in range(len(other.keys)):
            self.keys.append(other.keys[i])
            self.vectors.append(other.vectors[i])

    def __moveinit__(out self, mut other: Self):
        self.keys = other.keys^
        self.vectors = other.vectors^
        self.threshold = other.threshold

    def insert_atom(mut self, key: String, vec: Hypervector):
        self.keys.append(key)
        self.vectors.append(vec)

    def find_nearest(self, probe: Hypervector) -> String:
        """Hopfield clean-up / associative lookup returning the nearest stored key."""
        var best_key = String("")
        var best_sim: Float32 = -2.0

        for i in range(len(self.keys)):
            var sim = probe.cosine_similarity(self.vectors[i])
            if sim > best_sim:
                best_sim = sim
                best_key = self.keys[i]

        if best_sim >= self.threshold:
            return best_key
        return String("")
