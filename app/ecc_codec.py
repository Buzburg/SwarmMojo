"""Bifix-framing Reed-Solomon / BCH linear-block codec over GF(2^8) for Hypertokens.

Frames are *delimiter-prefix-free*: type byte at index 0 (0x00 = full data
block of k-1 payload bytes; 0xFF = terminator block, length byte at index
1 carries the explicit payload length 0..k-2, then the payload, then zero-
padding to fill k bytes). Two valid blocks cannot collide on a truncation
boundary because the type+length scheme uniquely classifies a block.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import List, Tuple, Union

logger = logging.getLogger(__name__)

N_MAX = 255
_PRIMITIVE = 0x11D

_gf_exp = [0] * 512
_gf_log = [0] * 256
def _build_tables() -> None:
    x = 1
    for i in range(255):
        _gf_exp[i] = x
        _gf_log[x] = i
        x <<= 1
        if x & 0x100:
            x ^= _PRIMITIVE
    for i in range(255, 512):
        _gf_exp[i] = _gf_exp[i - 255]
_build_tables()


def gf_add(a: int, b: int) -> int:
    return (a ^ b) & 0xFF


def gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _gf_exp[(_gf_log[a] + _gf_log[b]) % 255]


def gf_div(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("gf_div by zero")
    if a == 0:
        return 0
    return _gf_exp[(_gf_log[a] - _gf_log[b] + 255) % 255]


def gf_inv(a: int) -> int:
    if a == 0:
        raise ZeroDivisionError("gf_inv(0) undefined")
    return _gf_exp[(255 - _gf_log[a]) % 255]


def gf_pow(a: int, n: int) -> int:
    if n < 0:
        if a == 0:
            raise ZeroDivisionError("gf_pow(0, negative)")
        a = gf_inv(a)
        n = -n
    if n == 0:
        return 1
    if a == 0:
        return 0
    result = 1
    base = a
    while n > 0:
        if n & 1:
            result = gf_mul(result, base)
        base = gf_mul(base, base)
        n >>= 1
    return result


def gf_eval(coeffs: List[int], x: int) -> int:
    """Horner: coeffs[0] + coeffs[1]*x + ..."""
    acc = 0
    for c in reversed(coeffs):
        acc = gf_add(gf_mul(acc, x), c)
    return acc


# --- RS parameters ---

@dataclass(frozen=True)
class RSParams:
    """Reed-Solomon RS(255, k) with k = 255 - nsym, t = nsym // 2."""
    nsym: int
    @property
    def k(self) -> int:
        return N_MAX - self.nsym
    @property
    def t(self) -> int:
        return self.nsym // 2
    @property
    def n(self) -> int:
        return N_MAX


# --- RS encode: systematic short-division by generator polynomial ---

def _generator_poly(nsym: int) -> List[int]:
    """g(x) = (x + alpha^1)(x + alpha^2)...(x + alpha^nsym).

    Polynomial multiplication: C[i] = (g_old * (x + alpha))[i] = alpha*g_old[i]
    + g_old[i-1] (the very first factor (x + alpha) has constant alpha
    and x-coef 1, so each of g_old's coefficients contributes a constant
    term scaled by alpha and an x-shifted copy).
    """
    g = [1]
    for i in range(nsym):
        root = _gf_exp[i + 1]
        new_g = [0] * (len(g) + 1)
        for j in range(len(g)):
            new_g[j] = gf_add(new_g[j], gf_mul(root, g[j]))
            new_g[j + 1] = gf_add(new_g[j + 1], g[j])
        g = new_g
    return g


def rs_encode(msg: List[int], params: RSParams) -> bytearray:
    """Systematic Reed-Solomon encode.

    Produces codeword `[parity | message]` where the message occupies positions
    nsym..n-1 (high). The encoder:

    1. Places msg at high indices, runs synthetic division by g(x); the
       resulting low-index buffer is the remainder r(x) = (m(x) x^nsym) mod g(x).
    2. Re-concatenates `[r(x) | m(x)]` for the final codeword so the message
       is preserved at high indices for systematic recovery.

    Without the explicit re-attach, the long-division step zeroes the high-
    index positions and the output becomes `[parity | zeros]` (silly bug we
    already hit once).
    """
    if len(msg) != params.k:
        raise ValueError(f"msg length {len(msg)} != k {params.k}")
    g = _generator_poly(params.nsym)
    work = bytearray(params.n)
    for i in range(params.k):
        work[params.nsym + i] = msg[i] & 0xFF
    for i in range(params.n - 1, params.nsym - 1, -1):
        coef = work[i]
        if coef != 0:
            for j in range(params.nsym + 1):
                work[i - params.nsym + j] = gf_add(work[i - params.nsym + j], gf_mul(g[j], coef))
    # Re-attach the message at high indices so output is the canonical
    # systematic codeword `[r | m]` not `[r | 0]`.
    cw = bytearray(params.n)
    cw[:params.nsym] = work[:params.nsym]
    cw[params.nsym:] = bytearray(msg)
    return cw


# --- BM + Chien + Forney decoder ---

def _berlekamp_massey(syn: List[int]) -> Tuple[List[int], int]:
    """Berlekamp-Massey over GF(2^8). Returns (sigma, L).

    Follows the Huffman-Pless / Lin-Costello Variant 1 (monic-preserving) form:
    in the `2*L <= r` branch sigma is EXTENDED additively (sigma_old + (delta/b) *
    x^m * B) so its leading coefficient stays at 1; in the `else` branch sigma is
    also extended. sigma lives in locator form `sigma = Π (1 - X_i x)`.
    """
    n = len(syn)
    sigma = [1]
    B = [1]
    L = 0
    m = 1
    b = 1
    for r in range(n):
        delta = syn[r] & 0xFF
        for i in range(1, L + 1):
            if i < len(sigma) and (r - i) >= 0:
                delta = gf_add(delta, gf_mul(sigma[i], syn[r - i]))
        if delta == 0:
            m += 1
        elif 2 * L <= r:
            # Variant 1 (Huffman-Pless / Lin-Costello): monic-preserving.
            # sigma_new = sigma_old + (delta/b) * x^m * B (in char-2: + = -)
            T = sigma[:]
            coef = gf_div(delta, b)
            new_len = max(len(sigma), m + len(B))
            sigma = sigma + [0] * (new_len - len(sigma))
            for i in range(len(B)):
                if i + m < len(sigma):
                    sigma[i + m] = gf_add(sigma[i + m], gf_mul(coef, B[i]))
            L = r + 1 - L
            B = T
            m = 1
            b = delta
        else:
            # EXTEND branch: sigma_new = sigma + (delta/b) * x^m * B
            coef = gf_div(delta, b)
            new_len = max(len(sigma), m + len(B))
            sigma = sigma + [0] * (new_len - len(sigma))
            for i in range(len(B)):
                if i + m < len(sigma):
                    sigma[i + m] = gf_add(sigma[i + m], gf_mul(coef, B[i]))
            m += 1
    return sigma, L


def rs_decode(cw, params: RSParams) -> Tuple[List[int], int, bool]:
    cw_list = list(cw) if not isinstance(cw, list) else list(cw)
    cw_list = [c & 0xFF for c in cw_list]
    if len(cw_list) != params.n:
        raise ValueError(f"codeword length {len(cw_list)} != n {params.n}")
    cw_array = bytearray(cw_list)
    msg_default = [int(cw_array[params.nsym + i]) for i in range(params.k)]
    syn = [gf_eval(cw_list, _gf_exp[i + 1]) for i in range(params.nsym)]
    if all(s == 0 for s in syn):
        return msg_default, 0, True
    sigma, L = _berlekamp_massey(syn)
    if L < 0 or L > params.t:
        return msg_default, -1, False
    err_pos = []
    for pos in range(params.n):
        if gf_eval(sigma, _gf_exp[(255 - pos) % 255]) == 0:
            err_pos.append(pos)
    if len(err_pos) != L:
        return msg_default, -1, False
    poly_mult = [0] * (len(sigma) + params.nsym)
    for i in range(len(sigma)):
        for j in range(params.nsym):
            if i + j < len(poly_mult):
                poly_mult[i + j] = gf_add(poly_mult[i + j], gf_mul(sigma[i], syn[j]))
    omega = poly_mult[:params.nsym]
    sigma_deriv = []
    for j in range(1, len(sigma)):
        if j % 2 == 1:
            sigma_deriv.append(sigma[j])
        else:
            sigma_deriv.append(0)
    if not sigma_deriv:
        return msg_default, -1, False
    err_mag = []
    for pos in err_pos:
        X_inv = _gf_exp[(255 - pos) % 255]
        omega_at = gf_eval(omega, X_inv) if omega else 0
        deriv_at = gf_eval(sigma_deriv, X_inv)
        if deriv_at == 0:
            return msg_default, -1, False
        err_mag.append(gf_div(omega_at, deriv_at))
    corrected = bytearray(cw_array)
    for pos, mag in zip(err_pos, err_mag):
        corrected[pos] = gf_add(corrected[pos], mag)
    msg_partial = [int(corrected[params.nsym + i]) for i in range(params.k)]
    return msg_partial, len(err_pos), True


# --- Bifix-free framing ---

_TERM_BYTE = 0xFF
_DATA_BYTE = 0x00


def bifix_free_wrap(payload, nsym: int):
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("payload must be bytes or bytearray")
    params = RSParams(nsym=nsym)
    k = params.k
    blocks = []
    if not payload:
        msg = bytearray([_TERM_BYTE, 0]) + bytearray([0] * (k - 2))
        blocks.append(rs_encode(list(msg), params))
        return blocks
    chunk_size = k - 1
    n_full = len(payload) // chunk_size
    remainder_len = len(payload) - n_full * chunk_size
    for i in range(n_full):
        chunk = payload[i * chunk_size:(i + 1) * chunk_size]
        msg = bytearray([_DATA_BYTE]) + bytearray(chunk)
        blocks.append(rs_encode(list(msg), params))
    if remainder_len > 0:
        chunk = payload[n_full * chunk_size:]
        msg = bytearray([_TERM_BYTE, remainder_len]) + bytearray(chunk)
        if len(msg) < k:
            msg += bytearray([0] * (k - len(msg)))
        blocks.append(rs_encode(list(msg), params))
    else:
        msg = bytearray([_TERM_BYTE, 0]) + bytearray([0] * (k - 2))
        blocks.append(rs_encode(list(msg), params))
    return blocks


def bifix_free_unwrap(blocks, nsym: int):
    params = RSParams(nsym=nsym)
    out = bytearray()
    total_err = 0
    for block in blocks:
        cw_array = bytearray(block)
        msg, nc, ok = rs_decode(cw_array, params)
        if not ok:
            return bytes(out), -1, False
        total_err += nc
        if not msg:
            continue
        type_byte = msg[0]
        if type_byte == _DATA_BYTE:
            out.extend(msg[1:])
        elif type_byte == _TERM_BYTE:
            if len(msg) < 2:
                return bytes(out), -1, False
            length = msg[1]
            if length < 0 or length > len(msg) - 2:
                return bytes(out), -1, False
            out.extend(msg[2:2 + length])
            return bytes(out), total_err, True
        else:
            return bytes(out), -1, False
    return bytes(out), total_err, True


# --- ECCCodec dispatcher ---

@dataclass
class ECCCodecStats:
    encoded: int = 0
    decoded: int = 0
    corrected_bytes: int = 0
    failed: int = 0


class ECCCodec:
    """Reed-Solomon or BCH-styled block codec over GF(2^8) with bifix framing."""

    def __init__(self, mode: str = "RS", nsym: int = 32):
        mode = mode.upper()
        if mode not in ("RS", "BCH"):
            raise ValueError(f"mode must be 'RS' or 'BCH', got {mode!r}")
        if nsym <= 0 or nsym >= N_MAX:
            raise ValueError(f"nsym must be in (0, {N_MAX}), got {nsym}")
        self.mode = mode
        self.nsym = nsym
        self.params = RSParams(nsym=nsym)
        self.stats = ECCCodecStats()

    def _terminator_message(self, payload):
        k = self.params.k
        msg = bytearray([_TERM_BYTE, len(payload)]) + bytearray(payload)
        if len(msg) < k:
            msg += bytearray([0] * (k - len(msg)))
        return list(msg)

    def encode(self, payload):
        max_single = self.params.k - 2
        if len(payload) > max_single:
            raise ValueError(
                f"payload too large for single block: {len(payload)} > {max_single}"
            )
        cw = rs_encode(self._terminator_message(payload), self.params)
        self.stats.encoded += 1
        return bytes(cw)

    def decode(self, cw):
        cw_array = bytearray(cw)
        msg, nc, ok = rs_decode(cw_array, self.params)
        if not ok:
            self.stats.failed += 1
            return [], -1, False
        if not msg or msg[0] != _TERM_BYTE:
            self.stats.failed += 1
            return [], -1, False
        length = msg[1]
        if length < 0 or length > len(msg) - 2:
            self.stats.failed += 1
            return [], -1, False
        payload = msg[2:2 + length]
        self.stats.decoded += 1
        self.stats.corrected_bytes += max(0, nc)
        return payload, nc, True

    def encode_blocks(self, payload):
        blocks = bifix_free_wrap(payload, self.nsym)
        self.stats.encoded += len(blocks)
        return blocks

    def decode_blocks(self, blocks):
        out, err, ok = bifix_free_unwrap(blocks, self.nsym)
        if ok:
            self.stats.decoded += 1
            self.stats.corrected_bytes += max(0, err)
        else:
            self.stats.failed += 1
        return out, err, ok
