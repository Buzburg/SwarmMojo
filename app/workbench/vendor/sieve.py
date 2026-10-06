"""
mojo-sieve — Python Bridge & CLI
Streaming context compaction for terminal logs and compiler dumps.
"""

import os
import sys
import re
import time
import json
import argparse

ERROR_PATTERNS = [
    re.compile(r'(?i)\b(error|failed|failure|fatal|panic|exception|traceback|syntaxerror|typeerror)\b'),
    re.compile(r'^\s*-->\s*.*:\d+:\d+'),  # Rust compiler locator
    re.compile(r'^\s*at\s+.*\(.*:\d+:\d+\)'),  # Node/JS stack trace
    re.compile(r'^\s*File\s+".*",\s+line\s+\d+'), # Python stack trace
    re.compile(r'^[+-]{3}\s+[ab]/'), # Diff header
    re.compile(r'^@@\s+-\d+,\d+\s+\+\d+,\d+\s+@@') # Diff hunk
]

NOISE_PATTERNS = [
    re.compile(r'^\s*(ok|\.+)\s*$'),
    re.compile(r'(?i)(downloading|fetching|installing|extracted|\d+%\s*\[)'),
    re.compile(r'^\s*$')
]

def score_line(line: str) -> float:
    for pattern in ERROR_PATTERNS:
        if pattern.search(line):
            return 1.0

    for pattern in NOISE_PATTERNS:
        if pattern.search(line):
            return 0.0

    # Default moderate salience for informative lines
    return 0.2

def compact_text(text: str, context_window: int = 2, max_lines: int = 60) -> dict:
    start = time.perf_counter()
    lines = text.splitlines()
    total_lines = len(lines)
    
    if total_lines <= max_lines:
        return {
            "original_lines": total_lines,
            "compacted_lines": total_lines,
            "compression_ratio_pct": 0.0,
            "text": text,
            "latency_us": round((time.perf_counter() - start) * 1_000_000, 2)
        }

    scores = [score_line(line) for line in lines]
    
    # Expand retention window around high-priority lines
    retained_indices = set()
    for i, sc in enumerate(scores):
        if sc >= 0.8:
            for w in range(max(0, i - context_window), min(total_lines, i + context_window + 1)):
                retained_indices.add(w)

    # Always keep first 3 lines and last 5 lines for execution context
    for i in range(min(3, total_lines)):
        retained_indices.add(i)
    for i in range(max(0, total_lines - 5), total_lines):
        retained_indices.add(i)

    sorted_indices = sorted(retained_indices)
    
    compacted = []
    last_idx = -1
    for idx in sorted_indices:
        if last_idx != -1 and idx > last_idx + 1:
            compacted.append(f"... [{idx - last_idx - 1} repetitive lines truncated by mojo-sieve] ...")
        compacted.append(lines[idx])
        last_idx = idx

    compacted_text = "\n".join(compacted)
    saved_pct = ((total_lines - len(sorted_indices)) / total_lines) * 100.0 if total_lines else 0.0

    return {
        "original_lines": total_lines,
        "compacted_lines": len(sorted_indices),
        "compression_ratio_pct": round(saved_pct, 1),
        "text": compacted_text,
        "latency_us": round((time.perf_counter() - start) * 1_000_000, 2)
    }

def main():
    parser = argparse.ArgumentParser(description="mojo-sieve Terminal Output Compactor")
    parser.add_argument("input_file", nargs="?", help="Log file to compact (or stdin)")
    parser.add_argument("--max-lines", type=int, default=60)
    args = parser.parse_args()

    if args.input_file and os.path.exists(args.input_file):
        with open(args.input_file, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    elif not sys.stdin.isatty():
        content = sys.stdin.read()
    else:
        print("Usage: cat build.log | python sieve.py")
        sys.exit(0)

    res = compact_text(content, max_lines=args.max_lines)
    print(res["text"])
    print(f"\n[mojo-sieve: {res['original_lines']} -> {res['compacted_lines']} lines ({res['compression_ratio_pct']}% compressed) in {res['latency_us']/1000:.2f}ms]", file=sys.stderr)

if __name__ == "__main__":
    main()
