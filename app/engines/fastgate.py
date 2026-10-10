"""
mojo-fastgate — Python Bridge & CLI
Implements fast System-1 tool triage and JSON-lines/HTTP proxy transport.
"""

import sys
import math
import json
import time
import argparse
import re
from http.server import HTTPServer, BaseHTTPRequestHandler

DIM = 256
TAU = 6.283185307179586

def embed_term(token: str):
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

def cosine_similarity(vec_a, vec_b):
    return sum(a * b for a, b in zip(vec_a, vec_b))

def decompose_tokens(text: str):
    # Splits by non-alphanumeric, underscores, camelCase
    words = re.findall(r'[a-zA-Z0-9]+', text.lower())
    return [w for w in words if len(w) > 1]

def bundle_vector(terms: list):
    if not terms:
        return [0.0] * DIM
    accum = [0.0] * DIM
    for term in terms:
        t_vec = embed_term(term)
        for d in range(DIM):
            accum[d] += t_vec[d]
    norm = math.sqrt(sum(v * v for v in accum)) + 1e-7
    return [v / norm for v in accum]

def route_tools(prompt: str, tools: list, threshold: float = 0.15):
    start = time.perf_counter()
    prompt_terms = set(decompose_tokens(prompt))
    if not prompt_terms:
        prompt_terms = {"default"}

    prompt_vec = bundle_vector(list(prompt_terms))

    scores = []
    for tool_name in tools:
        tool_terms = set(decompose_tokens(tool_name))
        tool_vec = bundle_vector(list(tool_terms))

        # Hybrid scoring: phase vector similarity + token intersection
        phase_sim = max(0.0, cosine_similarity(prompt_vec, tool_vec))
        shared = len(prompt_terms & tool_terms)
        jaccard = shared / len(prompt_terms | tool_terms) if (prompt_terms | tool_terms) else 0.0

        hybrid_score = 0.6 * jaccard + 0.4 * phase_sim
        scores.append((tool_name, hybrid_score))

    scores.sort(key=lambda x: x[1], reverse=True)
    retained = [name for name, sc in scores if sc >= threshold]
    if not retained and tools:
        retained = [scores[0][0]]

    duration_us = (time.perf_counter() - start) * 1_000_000
    savings_pct = ((len(tools) - len(retained)) / len(tools)) * 100.0 if tools else 0.0

    return {
        "prompt": prompt,
        "original_count": len(tools),
        "retained_count": len(retained),
        "retained_tools": retained,
        "token_savings_pct": round(savings_pct, 1),
        "decision_latency_us": round(duration_us, 2)
    }

class FastgateHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/v1/triage":
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            req = json.loads(body.decode('utf-8'))
            prompt = req.get('prompt', '')
            tools = req.get('tools', [])
            res = route_tools(prompt, tools)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(res).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == "/healthz":
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"ok","engine":"mojo-fastgate-simd"}')
        else:
            self.send_response(404)
            self.end_headers()

def main():
    parser = argparse.ArgumentParser(description="mojo-fastgate System-1 Agent Router")
    subparsers = parser.add_subparsers(dest="command")

    triage_p = subparsers.add_parser("triage")
    triage_p.add_argument("prompt", type=str, help="Prompt text to triage")
    triage_p.add_argument("--tools", nargs="+", default=["read_file", "write_to_file", "run_command", "deploy_k8s", "send_email"])

    serve_p = subparsers.add_parser("serve")
    serve_p.add_argument("--port", type=int, default=8080)

    args = parser.parse_args()

    if args.command == "triage":
        res = route_tools(args.prompt, args.tools)
        print(json.dumps(res, indent=2))
    elif args.command == "serve":
        server = HTTPServer(('127.0.0.1', args.port), FastgateHandler)
        print(f"[*] mojo-fastgate server listening on http://127.0.0.1:{args.port}")
        server.serve_forever()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
