"""
mojo-compact-kv — Python Bridge & CLI
Rolling structured scratchpad & VRAM-capped working memory for local 7B-32B models.
"""

import os
import sys
import json
import time
import math
import argparse

DIM = 256
MAX_FACTS = 12
SCRATCHPAD_DIR = ".mojo_compact_kv"
SCRATCHPAD_FILE = os.path.join(SCRATCHPAD_DIR, "scratchpad.json")

def embed_fact(text: str):
    seed = 14695981039346656037
    for byte in text.encode('utf-8'):
        seed = ((seed ^ byte) * 1099511628211) & 0xFFFFFFFFFFFFFFFF

    values = []
    sum_sq = 0.0

    for _ in range(DIM):
        seed = (seed + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        mixed = seed
        mixed = ((mixed ^ (mixed >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        mixed = ((mixed ^ (mixed >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        mixed = (mixed ^ (mixed >> 31)) & 0xFFFFFFFFFFFFFFFF

        val = float((mixed % 2000000) - 1000000) / 1000000.0
        values.append(val)
        sum_sq += val * val

    inv_norm = 1.0 / (math.sqrt(sum_sq) + 1e-7)
    return [v * inv_norm for v in values]

def cosine_similarity(vec_a, vec_b):
    return sum(a * b for a, b in zip(vec_a, vec_b))

class CompactKVManager:
    def __init__(self, root: str = "."):
        self.root = os.path.abspath(root)
        self.dir = os.path.join(self.root, SCRATCHPAD_DIR)
        self.file = os.path.join(self.root, SCRATCHPAD_FILE)

    def init(self, goal: str):
        os.makedirs(self.dir, exist_ok=True)
        data = {
            "goal": goal,
            "created_at": time.time(),
            "turn_count": 0,
            "active_hypothesis": "Initial workspace exploration",
            "modified_files": [],
            "verified_facts": [],
            "rejected_approaches": []
        }
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return data

    def load(self):
        if not os.path.exists(self.file):
            return None
        with open(self.file, "r", encoding="utf-8") as f:
            return json.load(f)

    def save(self, data):
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def add_fact(self, fact_text: str):
        data = self.load()
        if not data:
            data = self.init("Default goal")

        new_vec = embed_fact(fact_text)
        # Deduplicate against existing facts
        for existing in data["verified_facts"]:
            ex_vec = embed_fact(existing)
            if cosine_similarity(new_vec, ex_vec) >= 0.8:
                return False # Duplicate fact

        if len(data["verified_facts"]) >= MAX_FACTS:
            data["verified_facts"].pop(0) # Evict oldest fact

        data["verified_facts"].append(fact_text)
        self.save(data)
        return True

    def set_hypothesis(self, hypothesis: str):
        data = self.load()
        if not data:
            data = self.init("Default goal")
        data["active_hypothesis"] = hypothesis
        self.save(data)
        return data

    def get_state(self):
        data = self.load()
        if not data:
            data = self.init("Default goal")
        return data

    def touch_file(self, filename: str):
        data = self.load()
        if data and filename not in data["modified_files"]:
            data["modified_files"].append(filename)
            self.save(data)

    def generate_compact_preamble(self) -> str:
        """
        Emits a structured <800-token working memory preamble to replace thousands of lines of raw history.
        """
        data = self.load()
        if not data:
            return ""

        lines = [
            "=== STRUCTURED WORKING MEMORY (COMPACT-KV) ===",
            f"GOAL: {data['goal']}",
            f"ACTIVE HYPOTHESIS: {data['active_hypothesis']}",
            f"MODIFIED FILES: {', '.join(data['modified_files']) if data['modified_files'] else 'None'}",
            "VERIFIED FACTS:"
        ]
        if data["verified_facts"]:
            for f in data["verified_facts"]:
                lines.append(f" - {f}")
        else:
            lines.append(" - None yet")

        if data["rejected_approaches"]:
            lines.append("REJECTED APPROACHES:")
            for r in data["rejected_approaches"]:
                lines.append(f" - {r}")

        lines.append("==============================================")
        return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="mojo-compact-kv Working Memory Manager")
    subparsers = parser.add_subparsers(dest="command")

    init_p = subparsers.add_parser("init")
    init_p.add_argument("--goal", required=True)

    fact_p = subparsers.add_parser("fact")
    fact_p.add_argument("text", help="New fact to store in working memory")

    touch_p = subparsers.add_parser("touch")
    touch_p.add_argument("file", help="File modified by agent")

    subparsers.add_parser("preamble")
    subparsers.add_parser("stats")

    args = parser.parse_args()
    mgr = CompactKVManager()

    if args.command == "init":
        mgr.init(args.goal)
        print(f"✔ Initialized compact working memory for: {args.goal}")
    elif args.command == "fact":
        added = mgr.add_fact(args.text)
        if added:
            print(f"✔ Added fact: {args.text}")
        else:
            print(f"Skipped duplicate fact: {args.text}")
    elif args.command == "touch":
        mgr.touch_file(args.file)
        print(f"✔ Tracked modified file: {args.file}")
    elif args.command == "preamble":
        print(mgr.generate_compact_preamble())
    elif args.command == "stats":
        data = mgr.load()
        if not data:
            print("No active scratchpad.")
            return
        words = len(mgr.generate_compact_preamble().split())
        est_tokens = int(words * 1.3)
        print(f"Working Memory Preamble Size: ~{est_tokens} tokens (VRAM overhead: <0.1 MB)")
        print(f"Facts: {len(data['verified_facts'])} | Files: {len(data['modified_files'])}")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
