"""
mojo-drift — Python Bridge & CLI
Real-time trajectory tracking and angular drift guardrails for AI coding agents.
"""

import os
import sys
import math
import time
import json
import re
import argparse

DIM = 256
RAD_TO_DEG = 57.29577951308232
DRIFT_DIR = ".mojo_drift"
SESSION_FILE = os.path.join(DRIFT_DIR, "session.json")

def embed_token(token: str):
    seed = 14695981039346656037
    for byte in token.encode('utf-8'):
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

def tokenize(text: str):
    words = re.findall(r'\b[a-zA-Z0-9_-]+\b', text.lower())
    return [w for w in words if len(w) > 1]

def bundle_text(tokens: list):
    if not tokens:
        tokens = ["default"]
    accum = [0.0] * DIM
    for tok in tokens:
        t_vec = embed_token(tok)
        for d in range(DIM):
            accum[d] += t_vec[d]
    norm = math.sqrt(sum(v * v for v in accum)) + 1e-7
    return [v / norm for v in accum]

def cosine_similarity(vec_a, vec_b):
    return sum(a * b for a, b in zip(vec_a, vec_b))

def evaluate_drift(goal: str, action: str, warn_threshold: float = 65.0, alert_threshold: float = 80.0):
    start = time.perf_counter()
    g_tokens = set(tokenize(goal))
    a_tokens = set(tokenize(action))

    g_vec = bundle_text(list(g_tokens))
    a_vec = bundle_text(list(a_tokens))

    dot = max(-1.0, min(1.0, cosine_similarity(g_vec, a_vec)))
    # Angular drift in degrees
    angle_deg = math.acos(dot) * RAD_TO_DEG

    # Lexical overlap bonus reduces artificial drift for direct token matches
    shared = len(g_tokens & a_tokens)
    if shared > 0:
        angle_deg = max(0.0, angle_deg - (shared * 15.0))

    verdict = "SAFE"
    if angle_deg >= alert_threshold:
        verdict = "DRIFT_ALERT"
    elif angle_deg >= warn_threshold:
        verdict = "WARN"

    duration_us = (time.perf_counter() - start) * 1_000_000

    return {
        "goal": goal,
        "action": action,
        "drift_angle_deg": round(angle_deg, 1),
        "verdict": verdict,
        "latency_us": round(duration_us, 2)
    }

class MojoDrift:
    """Object wrapper for mojo-drift guardrail checks."""
    def __init__(self, warn_threshold: float = 65.0, alert_threshold: float = 80.0):
        self.warn_threshold = warn_threshold
        self.alert_threshold = alert_threshold

    def evaluate_action(self, goal: str, action: str):
        res = evaluate_drift(goal, action, self.warn_threshold, self.alert_threshold)
        status = "safe"
        if res["verdict"] == "DRIFT_ALERT":
            status = "blocked"
        elif res["verdict"] == "WARN":
            status = "warn"
        return {
            "status": status,
            "verdict": res["verdict"],
            "drift_degrees": res["drift_angle_deg"],
            "latency_us": res["latency_us"],
            "goal": goal,
            "action": action,
        }

class SessionTracker:
    def __init__(self, root: str = "."):
        self.root = os.path.abspath(root)
        self.session_file = os.path.join(self.root, SESSION_FILE)

    def init_session(self, goal: str):
        os.makedirs(os.path.join(self.root, DRIFT_DIR), exist_ok=True)
        data = {
            "goal": goal,
            "created_at": time.time(),
            "steps": []
        }
        with open(self.session_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load_session(self):
        if not os.path.exists(self.session_file):
            return None
        with open(self.session_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def record_step(self, action: str):
        session = self.load_session()
        if not session:
            print("Error: No active session. Run `python drift.py init --goal '...'` first.")
            return None
        eval_res = evaluate_drift(session["goal"], action)
        session["steps"].append({
            "step": len(session["steps"]) + 1,
            "action": action,
            "drift_angle": eval_res["drift_angle_deg"],
            "verdict": eval_res["verdict"],
            "timestamp": time.time()
        })
        with open(self.session_file, "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2)
        return eval_res

def main():
    parser = argparse.ArgumentParser(description="mojo-drift Real-Time Trajectory Guardrail")
    subparsers = parser.add_subparsers(dest="command")

    check_p = subparsers.add_parser("check")
    check_p.add_argument("--goal", required=True, help="Original user task goal")
    check_p.add_argument("--action", required=True, help="Proposed agent action or tool call")

    init_p = subparsers.add_parser("init")
    init_p.add_argument("--goal", required=True, help="Anchor goal for session")

    step_p = subparsers.add_parser("step")
    step_p.add_argument("--action", required=True, help="Action taken by agent")

    subparsers.add_parser("status")

    args = parser.parse_args()
    tracker = SessionTracker()

    if args.command == "check":
        res = evaluate_drift(args.goal, args.action)
        print(json.dumps(res, indent=2))
        if res["verdict"] == "DRIFT_ALERT":
            sys.exit(1)
    elif args.command == "init":
        tracker.init_session(args.goal)
        print(f"✔ Initialized tracking session with goal: {args.goal}")
    elif args.command == "step":
        res = tracker.record_step(args.action)
        if res:
            print(f"Step {len(tracker.load_session()['steps'])}: [{res['verdict']}] Drift: {res['drift_angle_deg']}°")
            if res["verdict"] == "DRIFT_ALERT":
                print("⚠ WARNING: Agent has drifted significantly from the original goal!")
                sys.exit(1)
    elif args.command == "status":
        sess = tracker.load_session()
        if not sess:
            print("No active session found.")
            return
        print(f"Anchor Goal: {sess['goal']}")
        print(f"Total Steps: {len(sess['steps'])}")
        for st in sess["steps"]:
            print(f"  [{st['step']}] {st['verdict']:<11} | {st['drift_angle']}° | {st['action']}")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
