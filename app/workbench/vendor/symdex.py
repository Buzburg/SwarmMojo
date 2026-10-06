"""
mojo-symdex — Python Bridge & CLI
Zero-dependency in-memory code symbol & call-graph vector index.
"""

import os
import sys
import re
import json
import time
import argparse

SYMDEX_DIR = ".mojo_symdex"
INDEX_FILE = os.path.join(SYMDEX_DIR, "index.json")

SUPPORTED_EXTS = {".py", ".rs", ".go", ".js", ".ts", ".mojo"}
IGNORED_DIRS = {".git", ".mojo_symdex", "node_modules", "target", "__pycache__", ".build-venv"}

# Regex for function/class definitions
DEF_PATTERNS = [
    re.compile(r'^\s*def\s+([a-zA-Z0-9_]+)\s*\('),       # Python / Mojo
    re.compile(r'^\s*fn\s+([a-zA-Z0-9_]+)\s*(\(|<)'),     # Rust / Mojo
    re.compile(r'^\s*function\s+([a-zA-Z0-9_]+)\s*\('),  # JS / TS
    re.compile(r'^\s*func\s+([a-zA-Z0-9_]+)\s*\('),      # Go
    re.compile(r'^\s*class\s+([a-zA-Z0-9_]+)\b'),        # Python / JS / TS
    re.compile(r'^\s*struct\s+([a-zA-Z0-9_]+)\b'),       # Rust / Go / Mojo
]

CALL_PATTERN = re.compile(r'\b([a-zA-Z0-9_]+)\s*\(')

class SymdexIndex:
    def __init__(self, root: str = "."):
        self.root = os.path.abspath(root)
        self.symdex_dir = os.path.join(self.root, SYMDEX_DIR)
        self.index_file = os.path.join(self.root, INDEX_FILE)
        self.definitions = {} # sym -> list of {file, line}
        self.callers = {}     # callee -> list of {caller, file, line}
        self.callees = {}     # caller -> list of callees

    def build_index(self):
        start = time.perf_counter()
        self.definitions = {}
        self.callers = {}
        self.callees = {}

        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
            for fn in filenames:
                ext = os.path.splitext(fn)[1]
                if ext in SUPPORTED_EXTS:
                    full_path = os.path.join(dirpath, fn)
                    rel_path = os.path.relpath(full_path, self.root).replace("\\", "/")
                    self._index_file(full_path, rel_path)

        os.makedirs(self.symdex_dir, exist_ok=True)
        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump({
                "definitions": self.definitions,
                "callers": self.callers,
                "callees": self.callees,
                "timestamp": time.time()
            }, f, indent=2)

        return (time.perf_counter() - start) * 1000.0

    def _index_file(self, full_path: str, rel_path: str):
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception:
            return

        current_func = "global"

        for line_idx, line in enumerate(lines):
            line_no = line_idx + 1

            # Check definitions
            is_def = False
            for pat in DEF_PATTERNS:
                m = pat.match(line)
                if m:
                    sym_name = m.group(1)
                    current_func = sym_name
                    if sym_name not in self.definitions:
                        self.definitions[sym_name] = []
                    self.definitions[sym_name].append({
                        "file": rel_path,
                        "line": line_no
                    })
                    is_def = True
                    break

            if is_def:
                continue

            # Check calls
            for match in CALL_PATTERN.finditer(line):
                callee_name = match.group(1)
                # Ignore language keywords
                if callee_name in {"if", "for", "while", "switch", "return", "catch", "match", "print", "len"}:
                    continue
                if callee_name not in self.callers:
                    self.callers[callee_name] = []
                self.callers[callee_name].append({
                    "caller": current_func,
                    "file": rel_path,
                    "line": line_no
                })
                if current_func not in self.callees:
                    self.callees[current_func] = []
                if callee_name not in self.callees[current_func]:
                    self.callees[current_func].append(callee_name)

    def load_index(self):
        if not os.path.exists(self.index_file):
            self.build_index()
        with open(self.index_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.definitions = data.get("definitions", {})
            self.callers = data.get("callers", {})
            self.callees = data.get("callees", {})

    def find_symbol(self, sym_name: str):
        self.load_index()
        return self.definitions.get(sym_name, [])

    def get_callers(self, sym_name: str):
        self.load_index()
        return self.callers.get(sym_name, [])

    def get_callees(self, sym_name: str):
        self.load_index()
        return self.callees.get(sym_name, [])

def main():
    parser = argparse.ArgumentParser(description="mojo-symdex In-Memory Symbol & Call Graph Index")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("index")

    find_p = subparsers.add_parser("find")
    find_p.add_argument("symbol", help="Symbol name to find definition for")

    callers_p = subparsers.add_parser("callers")
    callers_p.add_argument("symbol", help="Symbol name to find callers of")

    callees_p = subparsers.add_parser("callees")
    callees_p.add_argument("symbol", help="Symbol name to find outgoing calls from")

    subparsers.add_parser("stats")

    args = parser.parse_args()
    idx = SymdexIndex()

    if args.command == "index":
        ms = idx.build_index()
        print(f"✔ Indexed {len(idx.definitions)} symbols and {len(idx.callers)} call references in {ms:.2f} ms")
    elif args.command == "find":
        defs = idx.find_symbol(args.symbol)
        if not defs:
            print(f"Symbol '{args.symbol}' not found.")
        else:
            print(f"Definitions for '{args.symbol}':")
            for d in defs:
                print(f"  {d['file']}:{d['line']}")
    elif args.command == "callers":
        callers = idx.get_callers(args.symbol)
        if not callers:
            print(f"No callers found for '{args.symbol}'.")
        else:
            print(f"Callers of '{args.symbol}':")
            for c in callers:
                print(f"  {c['file']}:{c['line']} (in {c['caller']})")
    elif args.command == "callees":
        callees = idx.get_callees(args.symbol)
        if not callees:
            print(f"No outgoing calls found for '{args.symbol}'.")
        else:
            print(f"Functions called by '{args.symbol}':")
            for cl in callees:
                print(f"  - {cl}")
    elif args.command == "stats":
        idx.load_index()
        print(f"Total defined symbols: {len(idx.definitions)}")
        print(f"Total call sites indexed: {sum(len(v) for v in idx.callers.values())}")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
