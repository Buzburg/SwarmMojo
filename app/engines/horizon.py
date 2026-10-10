"""
mojo-local-horizon — Python Bridge & CLI
State-machine DAG orchestrator and anti-loop circuit breaker for local 7B-32B models.
"""

import os
import sys
import json
import time
import math
import argparse

DIM = 256
HORIZON_DIR = ".mojo_horizon"
STATE_FILE = os.path.join(HORIZON_DIR, "state.json")

def embed_string(s: str):
    seed = 14695981039346656037
    for byte in s.encode('utf-8'):
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

class HorizonManager:
    def __init__(self, root: str = "."):
        self.root = os.path.abspath(root)
        self.dir = os.path.join(self.root, HORIZON_DIR)
        self.state_file = os.path.join(self.root, STATE_FILE)

    def init(self, goal: str):
        os.makedirs(self.dir, exist_ok=True)
        state = {
            "goal": goal,
            "created_at": time.time(),
            "nodes": [
                {"id": 1, "task": "Analyze workspace & locate relevant files", "status": "IN_PROGRESS"},
                {"id": 2, "task": "Implement code modification", "status": "PENDING"},
                {"id": 3, "task": "Verify changes with tests or linters", "status": "PENDING"}
            ],
            "active_node_id": 1,
            "action_history": [],
            "failed_attempts": []
        }
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        return state

    def load_state(self):
        if not os.path.exists(self.state_file):
            return None
        with open(self.state_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_state(self, state):
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    def record_action(self, action_cmd: str, success: bool = True, outcome: str = None):
        if outcome is not None or not isinstance(success, bool):
            action_full = f"{action_cmd}({success})" if str(success) else action_cmd
            is_success = str(outcome).lower() not in ("error", "failed", "failure", "false")
            action_cmd = action_full
            success = is_success

        state = self.load_state()
        if not state:
            state = self.init("Default agent task")

        cur_vec = embed_string(action_cmd.strip())
        
        # Check for loop against failed attempts
        is_loop = False
        for prev in state["failed_attempts"]:
            sim = cosine_similarity(cur_vec, prev["vector"])
            if sim >= 0.85:
                is_loop = True
                break

        if not success:
            state["failed_attempts"].append({
                "action": action_cmd,
                "vector": cur_vec,
                "timestamp": time.time()
            })

        state["action_history"].append({
            "action": action_cmd,
            "success": success,
            "node_id": state["active_node_id"],
            "timestamp": time.time()
        })
        self.save_state(state)

        return {
            "is_loop": is_loop,
            "active_node_id": state["active_node_id"],
            "action": action_cmd
        }

    def advance_node(self):
        state = self.load_state()
        if not state:
            return False
        cur_id = state["active_node_id"]
        for node in state["nodes"]:
            if node["id"] == cur_id:
                node["status"] = "COMPLETED"
            elif node["id"] == cur_id + 1:
                node["status"] = "IN_PROGRESS"
                state["active_node_id"] = node["id"]
                break
        self.save_state(state)
        return True

def main():
    parser = argparse.ArgumentParser(description="mojo-local-horizon DAG Orchestrator")
    subparsers = parser.add_subparsers(dest="command")

    init_p = subparsers.add_parser("init")
    init_p.add_argument("--goal", required=True)

    step_p = subparsers.add_parser("step")
    step_p.add_argument("--action", required=True)
    step_p.add_argument("--failed", action="store_true")

    subparsers.add_parser("advance")
    subparsers.add_parser("status")

    args = parser.parse_args()
    mgr = HorizonManager()

    if args.command == "init":
        state = mgr.init(args.goal)
        print(f"✔ Initialized DAG with 3 atomic tasks for: {args.goal}")
    elif args.command == "step":
        res = mgr.record_action(args.action, success=(not args.failed))
        if res.get("is_loop"):
            print("🛑 [CIRCUIT BREAKER TRIGGERED] Semantic loop detected! Model repeated a failed approach.")
            print("Adversarial Intervention: Forbid repeating this command. Hypothesize a new strategy.")
            sys.exit(1)
        else:
            print(f"✔ Recorded step for Node {res.get('active_node_id')}: {args.action}")
    elif args.command == "advance":
        mgr.advance_node()
        state = mgr.load_state()
        print(f"✔ Advanced to Node {state['active_node_id']}")
    elif args.command == "status":
        state = mgr.load_state()
        if not state:
            print("No active state.")
            return
        print(f"Goal: {state['goal']}")
        print(f"Active Node: {state['active_node_id']}")
        for n in state["nodes"]:
            status_sym = "✔" if n["status"] == "COMPLETED" else "►" if n["status"] == "IN_PROGRESS" else " "
            print(f" [{status_sym}] Node {n['id']}: {n['task']} ({n['status']})")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
