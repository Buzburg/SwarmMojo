"""High-Performance 16,384-bit SIMD Vector Symbolic Architecture (VSA),
Telegraphic Symbolic Language (TSL) Protocol, and Adaptive Speculative Controller.

Ported from Swarmojo and New Harness (Edge Connection) into Custom Omarchy OS:
1. 16,384-bit Binary Spatter Code (BSC) Vector Symbolic Architecture (HypervectorBSC)
2. Hopfield cleanup associative memory bank (HolographicMemoryBank)
3. Zero-overhead streaming FSM parser for TSL tokens (TSLStreamParser)
4. Adaptive speculative decoding draft controller (AdaptiveSpeculativeController)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

D_BITS = 16384
D_WORDS = 256  # 256 x 64-bit uints = 16,384 bits


@dataclass
class HypervectorBSC:
    """16,384-bit Binary Spatter Code (BSC) hypervector.
    Backed by 256 64-bit integers for hardware-accelerated bitwise operations.
    """
    words: List[int] = field(default_factory=lambda: [0] * D_WORDS)

    @classmethod
    def from_seed(cls, seed: str) -> HypervectorBSC:
        """Deterministically generates a pseudo-orthogonal hypervector from a string seed."""
        state = 0x9E3779B97F4A7C15
        for b in seed.encode("utf-8"):
            state = ((state ^ b) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
            state = (state ^ (state >> 27)) & 0xFFFFFFFFFFFFFFFF

        words = [0] * D_WORDS
        for w in range(D_WORDS):
            state = (state + 0x9E3779B97F4A7C15 + w) & 0xFFFFFFFFFFFFFFFF
            z = state
            z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
            z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
            z = (z ^ (z >> 31)) & 0xFFFFFFFFFFFFFFFF
            words[w] = z
        return cls(words=words)

    def bind(self, other: HypervectorBSC) -> HypervectorBSC:
        """XOR Binding (A ^ B). Maps two hypervectors to an orthogonal composite vector.
        Self-inverse property: (A ^ B) ^ B = A.
        """
        new_words = [a ^ b for a, b in zip(self.words, other.words)]
        return HypervectorBSC(words=new_words)

    def hamming_distance(self, other: HypervectorBSC) -> int:
        """Normalized bitwise Hamming distance across all 16,384 bits."""
        total_diff = 0
        for a, b in zip(self.words, other.words):
            diff = a ^ b
            total_diff += diff.bit_count()
        return total_diff

    def cosine_similarity(self, other: HypervectorBSC) -> float:
        """Bipolar cosine similarity equivalent: cos(theta) = 1.0 - 2.0 * (Hamming / D).
        1.0 = identical, 0.0 = orthogonal (8,192 bit diffs), -1.0 = exact inverse.
        """
        dist = self.hamming_distance(other)
        return 1.0 - (2.0 * dist / D_BITS)

    def permute(self, shift: int = 1) -> HypervectorBSC:
        """Cyclic bit permutation for role-filler binding (e.g., Subject vs Relation vs Object)."""
        word_shift = (shift // 64) % D_WORDS
        bit_shift = shift % 64
        result = [0] * D_WORDS
        for i in range(D_WORDS):
            src_idx = (i + D_WORDS - word_shift) % D_WORDS
            next_idx = (src_idx + 1) % D_WORDS
            low_bits = (self.words[src_idx] << bit_shift) & 0xFFFFFFFFFFFFFFFF
            high_bits = (self.words[next_idx] >> (64 - bit_shift)) if bit_shift > 0 else 0
            result[i] = low_bits | high_bits
        return HypervectorBSC(words=result)


class HolographicMemoryBank:
    """Associative memory store with Hopfield cleanup threshold for 16k-bit hypervectors."""

    def __init__(self, threshold: float = 0.15):
        self.threshold = threshold
        self.atoms: Dict[str, HypervectorBSC] = {}

    def insert(self, key: str, vec: HypervectorBSC) -> None:
        self.atoms[key] = vec

    def insert_symbol(self, key: str) -> HypervectorBSC:
        vec = HypervectorBSC.from_seed(key)
        self.atoms[key] = vec
        return vec

    def find_nearest(self, probe: HypervectorBSC) -> Tuple[Optional[str], float]:
        """Finds the stored atom with the highest cosine similarity to the probe vector."""
        best_key = None
        best_sim = -2.0
        for key, vec in self.atoms.items():
            sim = probe.cosine_similarity(vec)
            if sim > best_sim:
                best_sim = sim
                best_key = key
        if best_sim >= self.threshold:
            return best_key, best_sim
        return None, best_sim


@dataclass
class ParsedTriple:
    subject: str
    relation: str
    object: str


class TSLStreamParser:
    """Streaming byte-level Finite State Machine (FSM) parser for TSL tokens.
    Parses [OUT:"..."] text streams and [ADD:(subject relation object)] memory triples.
    """

    STATE_SEEKING = 0
    STATE_TAG_IDENT = 1
    STATE_STREAM_OUT = 2
    STATE_BUFFER_ADD = 3

    def __init__(self):
        self.state = self.STATE_SEEKING
        self.tag_buffer = ""
        self.triple_buffer = ""
        self.output_text = ""
        self.in_quotes = False
        self.bound_triples: List[ParsedTriple] = []

    def feed(self, chunk: str) -> Tuple[str, List[ParsedTriple]]:
        """Feeds an incoming token chunk into the FSM. Returns new streamed text and new triples."""
        emitted_text = ""
        new_triples = []

        for ch in chunk:
            if self.state == self.STATE_SEEKING:
                if ch == "[":
                    self.state = self.STATE_TAG_IDENT
                    self.tag_buffer = ""

            elif self.state == self.STATE_TAG_IDENT:
                if ch == "]":
                    self.state = self.STATE_SEEKING
                else:
                    self.tag_buffer += ch
                    if self.tag_buffer == "OUT:":
                        self.state = self.STATE_STREAM_OUT
                        self.in_quotes = False
                        self.tag_buffer = ""
                    elif self.tag_buffer == "ADD:":
                        self.state = self.STATE_BUFFER_ADD
                        self.triple_buffer = ""
                        self.tag_buffer = ""

            elif self.state == self.STATE_STREAM_OUT:
                if ch == '"':
                    self.in_quotes = not self.in_quotes
                elif ch == "]" and not self.in_quotes:
                    self.state = self.STATE_SEEKING
                else:
                    emitted_text += ch
                    self.output_text += ch

            elif self.state == self.STATE_BUFFER_ADD:
                if ch == "(":
                    self.triple_buffer = ""
                elif ch == ")":
                    raw = self.triple_buffer.strip()
                    if raw:
                        parts = raw.split()
                        if len(parts) >= 3:
                            triple = ParsedTriple(parts[0], parts[1], parts[2])
                            self.bound_triples.append(triple)
                            new_triples.append(triple)
                    self.triple_buffer = ""
                elif ch == "]":
                    self.state = self.STATE_SEEKING
                else:
                    self.triple_buffer += ch

        return emitted_text, new_triples


def build_tsl_prompt(
    role: str,
    repo_ast_context: str = "",
    mem_triples: Optional[List[str]] = None,
    goal: str = "",
) -> str:
    """Assembles a compact Telegraphic Symbolic Language payload."""
    lines = [f"[ROLE:{role}]"]
    if repo_ast_context:
        lines.append(f"[REPO_AST:\n{repo_ast_context}]")
    if mem_triples:
        trip_str = "".join(f"({t})" for t in mem_triples)
        lines.append(f"[MEM:{trip_str}]")
    if goal:
        lines.append(f'[GOAL:"{goal}"]')
    lines.append('Respond strictly in TSL format: [OUT:"..."][ADD:(s r o)]')
    return "\n".join(lines)


class AdaptiveSpeculativeController:
    """Adaptive Speculative Decoding Controller ported from New Harness (Edge Connection).
    Dynamically tunes the draft token lookahead length (K) based on real-time token
    acceptance rates on unified memory APU/CPU architectures.
    """

    def __init__(
        self,
        min_draft_tokens: int = 1,
        max_draft_tokens: int = 8,
        target_acceptance_rate: float = 0.65,
    ):
        self.min_draft_tokens = min_draft_tokens
        self.max_draft_tokens = max_draft_tokens
        self.target_acceptance_rate = target_acceptance_rate
        self.current_draft_tokens = 4
        self.total_accepted = 0
        self.total_drafted = 0

    def record_step(self, drafted: int, accepted: int) -> int:
        """Records acceptance count and updates optimal lookahead K."""
        self.total_drafted += drafted
        self.total_accepted += accepted

        step_rate = accepted / max(1, drafted)
        if step_rate >= self.target_acceptance_rate and self.current_draft_tokens < self.max_draft_tokens:
            self.current_draft_tokens += 1
        elif step_rate < (self.target_acceptance_rate - 0.2) and self.current_draft_tokens > self.min_draft_tokens:
            self.current_draft_tokens -= 1

        return self.current_draft_tokens

    @property
    def overall_acceptance_rate(self) -> float:
        return self.total_accepted / max(1, self.total_drafted)
