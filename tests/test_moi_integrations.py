r"""Comprehensive verification suite for integrations ported from MoI and Random Extra.

Tests:
1. DARK Reasoning Bridge (Deductive/Abductive template matching, confidence, and format)
2. ProcessSandbox (Subprocess isolation, worker protocol, error capture)
3. NESTstack PersonalityProfile (4-axis MBTI, emotional dimensions, gut feeling)
4. Reed-Solomon Codec (GF(2^8) Galois Field arithmetic, error correction)
5. Phase-Encoded HRR (Phase vectors, circular convolution bind/unbind)
"""

import pytest
import math
import numpy as np

from app.dark_reasoner import DARKReasoningBridge, format_dark_block, dark_bridge
from app.process_sandbox import ProcessSandbox
from app.nest_soul import PersonalityProfile, default_omarchy_soul
from app.ecc_codec import RSParams, rs_encode, rs_decode
from app.holographic_phase import encode_atom, bind, unbind, similarity


# Helper target for sandbox execution test
def sample_sandbox_target(a: int, b: int) -> int:
    return a * 10 + b


def test_dark_reasoning_bridge():
    bridge = DARKReasoningBridge(
        extra_premises=[
            "Omarchy OS is a sovereign local autonomous operating system.",
            "RWKV7 can provide linear-time recurrence without quadratic attention cost.",
            "Strix Halo provides 128GB unified memory.",
        ],
        extra_rules=[
            "High token throughput occurs when the model runs on unified APU memory.",
            "Context blowout is prevented by linear-time recurrent states.",
        ],
    )

    # 1. Deductive Capability Query
    res_cap = bridge.reason("Can you provide linear-time recurrence?", mode="deductive")
    assert res_cap["mode"] == "deductive"
    assert "SUPPORTED" in res_cap["conclusion"]
    assert res_cap["confidence"] >= 0.65

    # 2. Deductive Identity Query
    res_id = bridge.reason("What is Omarchy OS?", mode="deductive")
    assert "Omarchy OS" in res_id["conclusion"]

    # 3. Abductive Causal Query
    res_why = bridge.reason("Why did high token throughput occur?", mode="abductive")
    assert res_why["mode"] == "abductive"
    assert "unified APU memory" in res_why["conclusion"]

    # 4. Formatted block check
    block = format_dark_block(res_cap)
    assert "[DARK:deductive" in block
    assert "[/DARK]" in block


def test_process_sandbox():
    sb = ProcessSandbox(max_workers=2)
    # Register our test function
    sb.register("sample_calc", "tests.test_moi_integrations", "sample_sandbox_target")

    # Test synchronous invocation in separate subprocess
    resp = sb.invoke_sync("sample_calc", {"a": 5, "b": 7}, timeout=5.0)
    assert resp["ok"] is True
    assert resp["result"] == 57

    # Test unknown tool handling
    resp_bad = sb.invoke_sync("non_existent_tool", {}, timeout=2.0)
    assert resp_bad["ok"] is False
    assert "Unknown tool" in resp_bad["error"]


def test_nest_soul_profile():
    # Test INTP profile
    intp = PersonalityProfile(
        axis_weights=(-0.8, -0.7, 0.9, -0.4),  # I, N, T, P
        turn_count=5,
        label="Architect",
    )
    assert intp.derive_mbti() == "INTP"
    traits = intp.trait_lines()
    assert len(traits) == 4
    assert any("Reflective" in t for t in traits)

    # Gut feeling calculation
    gut = intp.gut_feeling()
    assert 0.0 <= gut <= 1.0

    # Emotions
    emotions = intp.emotion_tags()
    assert len(emotions) == 4

    # Prompt block formatting
    block = intp.format_prompt_block()
    assert "[SOUL:archetype=INTP" in block
    assert "[/SOUL]" in block

    # Snapshot serialization roundtrip
    snap = intp.snapshot_dict()
    restored = PersonalityProfile.from_snapshot(snap)
    assert restored.derive_mbti() == "INTP"


def test_reed_solomon_ecc_correction():
    # RS(255, 223) with nsym=32, capable of correcting up to 16 byte errors
    params = RSParams(nsym=32)
    msg = [i % 256 for i in range(params.k)]

    # Systematic encode: codeword length = 255
    codeword = rs_encode(msg, params)
    assert len(codeword) == params.n

    # Corrupt up to 10 bytes (within error capacity t=16)
    corrupted = list(codeword)
    for err_idx in range(10):
        corrupted[err_idx * 5] ^= 0xFF

    # Decode and verify error recovery
    recovered_msg, num_errs, ok = rs_decode(corrupted, params)
    assert ok is True
    assert num_errs == 10
    assert recovered_msg == msg


def test_phase_holographic_hrr():
    dim = 512
    atom_a = encode_atom("Agent_Goal", dim=dim)
    atom_b = encode_atom("Execute_Step", dim=dim)
    atom_c = encode_atom("Agent_Goal", dim=dim)

    # Self identity
    assert np.allclose(atom_a, atom_c)
    assert pytest.approx(similarity(atom_a, atom_c), 0.001) == 1.0

    # Orthogonality between distinct atoms
    sim_ab = similarity(atom_a, atom_b)
    assert abs(sim_ab) < 0.2

    # Circular convolution bind: C = A * B
    bound = bind(atom_a, atom_b)
    assert abs(similarity(bound, atom_a)) < 0.2

    # Circular correlation unbind: (A * B) - B ≈ A
    unbound = unbind(bound, atom_b)
    assert similarity(unbound, atom_a) > 0.99
