"""
mojo-titans — Python Bridge & CLI
Implementation of "Titans: Learning to Memorize at Test Time" (arXiv:2501.00663).
Neural Long-Term Memory module using online test-time gradient descent with momentum and adaptive forgetting.
"""

import os
import sys
import re
import json
import math
import time
import struct
import hashlib
import argparse

DIM = 32
MATRIX_SIZE = DIM * DIM
TITANS_DIR = ".mojo_titans"
WEIGHTS_FILE = os.path.join(TITANS_DIR, "weights.bin")
MOMENTUM_FILE = os.path.join(TITANS_DIR, "momentum.bin")
META_FILE = os.path.join(TITANS_DIR, "meta.json")


def l2_norm(vec: list) -> float:
    return math.sqrt(sum(x * x for x in vec))


def cosine_similarity(vec_a: list, vec_b: list) -> float:
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    na = l2_norm(vec_a)
    nb = l2_norm(vec_b)
    if na < 1e-8 or nb < 1e-8:
        return 0.0
    return dot / (na * nb)


def encode_unit_vector(text: str, dim: int = DIM) -> list:
    """Projects text into an L2-normalized unit vector in R^dim."""
    vec = [0.0] * dim
    tokens = re.findall(r"[a-z0-9_]+", text.lower())
    if not tokens:
        tokens = [text.lower()]

    for tok in tokens:
        h = int(hashlib.sha256(tok.encode("utf-8")).hexdigest(), 16)
        for j in range(4):
            idx = (h + j * 13) % dim
            sign = 1.0 if ((h >> (j + 4)) & 1) == 0 else -1.0
            vec[idx] += sign

    norm = l2_norm(vec)
    if norm < 1e-8:
        vec[0] = 1.0
        return vec
    return [x / norm for x in vec]


def matvec(matrix: list, vec: list, dim: int = DIM) -> list:
    """Computes y = M * x for flat row-major matrix of shape (dim, dim)."""
    out = [0.0] * dim
    for r in range(dim):
        offset = r * dim
        acc = 0.0
        for c in range(dim):
            acc += matrix[offset + c] * vec[c]
        out[r] = acc
    return out


def titans_memorize_step(
    weights: list,
    momentum: list,
    key_vec: list,
    val_vec: list,
    eta: float = 0.80,
    theta: float = 0.65,
    alpha: float = 0.01,
    dim: int = DIM
) -> dict:
    """
    Executes the exact Titans Test-Time Training (TTT) memory update:
      1. Surprise Residual: e_t = M_{t-1} k_t - v_t
      2. Surprise Loss:     l_t = 0.5 * ||e_t||_2^2
      3. Momentum Update:   S_t = eta * S_{t-1} - theta * (e_t @ k_t^T)
      4. Memory Update:     M_t = (1 - alpha) * M_{t-1} + S_t
    """
    pred_pre = matvec(weights, key_vec, dim)
    err = [p - v for p, v in zip(pred_pre, val_vec)]
    surprise_loss = 0.5 * sum(e * e for e in err)

    retain = 1.0 - alpha
    for r in range(dim):
        offset = r * dim
        e_r = err[r]
        for c in range(dim):
            idx = offset + c
            grad = e_r * key_vec[c]
            s_new = (eta * momentum[idx]) - (theta * grad)
            w_new = (retain * weights[idx]) + s_new
            momentum[idx] = s_new
            weights[idx] = w_new

    pred_post = matvec(weights, key_vec, dim)
    post_loss = 0.5 * sum((p - v) ** 2 for p, v in zip(pred_post, val_vec))
    weight_norm = math.sqrt(sum(w * w for w in weights))

    return {
        "surprise_loss": round(surprise_loss, 6),
        "post_update_loss": round(post_loss, 6),
        "weight_norm": round(weight_norm, 4),
        "is_surprising": surprise_loss > 0.15
    }


class TitansMemoryManager:
    def __init__(self, root: str = "."):
        self.root = os.path.abspath(root)
        self.t_dir = os.path.join(self.root, TITANS_DIR)
        self.w_file = os.path.join(self.root, WEIGHTS_FILE)
        self.m_file = os.path.join(self.root, MOMENTUM_FILE)
        self.meta_file = os.path.join(self.root, META_FILE)

    def init(self):
        os.makedirs(self.t_dir, exist_ok=True)
        zeros = [0.0] * MATRIX_SIZE
        self._save_bin(self.w_file, zeros)
        self._save_bin(self.m_file, zeros)
        meta = {
            "steps": 0,
            "stored_items": [],
            "last_surprise": 0.0
        }
        self._save_meta(meta)
        return meta

    def _save_bin(self, path: str, vec: list):
        with open(path, "wb") as f:
            f.write(struct.pack(f"{len(vec)}f", *vec))

    def _load_bin(self, path: str) -> list:
        if not os.path.exists(path):
            return [0.0] * MATRIX_SIZE
        with open(path, "rb") as f:
            raw = f.read()
            return list(struct.unpack(f"{len(raw)//4}f", raw))

    def _load_meta(self) -> dict:
        if not os.path.exists(self.meta_file):
            return self.init()
        with open(self.meta_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_meta(self, meta: dict):
        os.makedirs(self.t_dir, exist_ok=True)
        with open(self.meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

    def memorize(
        self,
        key_text: str,
        value_text: str,
        eta: float = 0.80,
        theta: float = 0.65,
        alpha: float = 0.01
    ) -> dict:
        if not os.path.exists(self.w_file):
            self.init()

        weights = self._load_bin(self.w_file)
        momentum = self._load_bin(self.m_file)
        meta = self._load_meta()

        k_vec = encode_unit_vector(key_text)
        v_vec = encode_unit_vector(value_text)

        metrics = titans_memorize_step(
            weights, momentum, k_vec, v_vec, eta=eta, theta=theta, alpha=alpha
        )

        self._save_bin(self.w_file, weights)
        self._save_bin(self.m_file, momentum)

        meta["steps"] += 1
        meta["last_surprise"] = metrics["surprise_loss"]
        # Store value catalog for human-readable decoding of associative vector output
        existing_keys = [item["key"] for item in meta["stored_items"]]
        if key_text not in existing_keys:
            meta["stored_items"].append({"key": key_text, "value": value_text})
        else:
            for item in meta["stored_items"]:
                if item["key"] == key_text:
                    item["value"] = value_text

        self._save_meta(meta)
        return metrics

    def recall(self, query_text: str) -> dict:
        weights = self._load_bin(self.w_file)
        meta = self._load_meta()
        q_vec = encode_unit_vector(query_text)
        y_vec = matvec(weights, q_vec)

        best_match = None
        best_sim = -1.0
        for item in meta.get("stored_items", []):
            cand_vec = encode_unit_vector(item["value"])
            sim = cosine_similarity(y_vec, cand_vec)
            if sim > best_sim:
                best_sim = sim
                best_match = item

        return {
            "query": query_text,
            "retrieved_vector_norm": round(l2_norm(y_vec), 4),
            "best_match": best_match,
            "confidence": round(max(0.0, best_sim), 4)
        }


class TitansMemory(TitansMemoryManager):
    def load(self):
        if not os.path.exists(self.w_file):
            return self.init()
        return self._load_meta()

    def save(self):
        pass

    def write(self, fact: str, key: str = None) -> float:
        k = key or fact[:32]
        res = self.memorize(key_text=k, value_text=fact)
        return float(res.get("surprise_loss", 0.0))

    def read(self, query: str, top_k: int = 5) -> list:
        res = self.recall(query)
        if res.get("best_match"):
            return [res["best_match"]]
        return []


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="mojo-titans: Test-Time Neural Memory (arXiv:2501.00663)")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init", help="Initialize Titans Long-Term Neural Memory")

    mem_p = subparsers.add_parser("memorize", help="Memorize key-value association via test-time gradient step")
    mem_p.add_argument("--key", required=True)
    mem_p.add_argument("--value", required=True)
    mem_p.add_argument("--eta", type=float, default=0.80, help="Surprise momentum decay")
    mem_p.add_argument("--theta", type=float, default=0.65, help="Test-time learning rate")
    mem_p.add_argument("--alpha", type=float, default=0.01, help="Adaptive forgetting gate")

    rec_p = subparsers.add_parser("recall", help="Query neural memory M_t * q_t")
    rec_p.add_argument("--query", required=True)

    subparsers.add_parser("status", help="Inspect neural memory state")

    args = parser.parse_args()
    mgr = TitansMemoryManager()

    if args.command == "init":
        mgr.init()
        print(f"[+] Initialized Titans Neural Memory ({DIM}x{DIM} = {MATRIX_SIZE} float32 parameters)")

    elif args.command == "memorize":
        start = time.perf_counter()
        res = mgr.memorize(args.key, args.value, eta=args.eta, theta=args.theta, alpha=args.alpha)
        us = (time.perf_counter() - start) * 1_000_000
        print(f"[+] Titans Test-Time Update Completed in {us:.1f} us")
        print(f"  Surprise Loss (Pre-Update):  {res['surprise_loss']:.6f}")
        print(f"  Recall Loss (Post-Update):   {res['post_update_loss']:.6f}")
        print(f"  Memory Matrix Norm ||M||_F:  {res['weight_norm']:.4f}")

    elif args.command == "recall":
        res = mgr.recall(args.query)
        print(f"=== Titans Associative Recall ===")
        print(f"  Query:      {res['query']}")
        if res["best_match"]:
            print(f"  Recalled:   {res['best_match']['value']} (Confidence: {res['confidence']:.4f})")
        else:
            print("  Recalled:   [Empty Memory]")

    elif args.command == "status":
        meta = mgr._load_meta()
        print(f"Titans Steps: {meta['steps']} | Stored Associations: {len(meta['stored_items'])} | Last Surprise: {meta['last_surprise']}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
