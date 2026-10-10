"""Bounded tools. Model proposals are data, never implicitly shell code."""

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import stat
import subprocess
import tempfile
import threading


READ_TOOLS = {"list_files", "read_file", "read_lines", "search", "git_status", "system_info", "desktop_state", "evidence_search", "verify_claim", "review", "recall"}
SPECS = {
    "list_files": {"path": str}, "read_file": {"path": str},
    "read_lines": {"path": str, "start_line": int, "end_line": int},
    "search": {"path": str, "text": str}, "git_status": {}, "system_info": {}, "desktop_state": {},
    "write_file": {"path": str, "content": str, "expected_sha256": str},
    "edit_file": {"path": str, "old_text": str, "new_text": str, "expected_sha256": str},
    "run_command": {"argv": list}, "focus_window": {"title": str},
    "evidence_search": {"path": str, "query": str},
    "verify_claim": {"path": str, "claim": str, "quote": str}, "review": {"path": str},
    "recall": {"query": str},
}


def validate_action(action):
    if not isinstance(action, dict) or set(action) != {"tool", "args"}:
        raise ValueError("Action must contain only tool and args")
    tool, args = action["tool"], action["args"]
    if not isinstance(tool, str) or tool not in SPECS or not isinstance(args, dict):
        raise ValueError("Unknown tool or invalid arguments")
    if set(args) != set(SPECS[tool]):
        raise ValueError(f"Expected arguments for {tool}: {list(SPECS[tool])}")
    for key, typ in SPECS[tool].items():
        if type(args[key]) is not typ:
            raise ValueError(f"Invalid type for {key}")
        if typ is str and ("\x00" in args[key] or len(args[key].encode()) > 65536):
            raise ValueError("Argument contains NUL or exceeds 64 KiB")
    if tool == "run_command":
        argv = args["argv"]
        if (not 1 <= len(argv) <= 64 or any(type(x) is not str or not x or "\x00" in x or len(x)>4096 for x in argv)):
            raise ValueError("argv must be 1..64 nonempty bounded strings")
    if tool == "write_file" and args["expected_sha256"] != "missing" and not re.fullmatch(r"[a-f0-9]{64}", args["expected_sha256"]):
        raise ValueError("write_file requires the read_file SHA256, or 'missing' for a new file")
    if tool == 'edit_file':
        if not re.fullmatch(r'[a-f0-9]{64}', args['expected_sha256']):
            raise ValueError('edit_file requires an observed SHA256 of an existing file')
        if not args['old_text'] or args['old_text'] == args['new_text']:
            raise ValueError('edit_file needs nonempty old_text and a different replacement')
    if tool == 'read_lines' and not (1 <= args['start_line'] <= args['end_line'] <= 2_000_000
                                    and args['end_line']-args['start_line'] < 200):
        raise ValueError('read_lines needs a one-based range of at most 200 lines')
    if tool == "search" and not args["text"]:
        raise ValueError("Search text must be nonempty")
    return action


def bounded_process(argv, cwd=None, timeout=20, limit=16000):
    """Drain pipes without holding unlimited output; terminate the process group."""
    proc = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, start_new_session=os.name != "nt", shell=False)
    chunks = bytearray()
    overflow = [False]

    def drain():
        while True:
            chunk = proc.stdout.read(4096)
            if not chunk:
                break
            room = max(0, limit - len(chunks))
            chunks.extend(chunk[:room])
            if len(chunk) > room:
                overflow[0] = True

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
    finally:
        if os.name != "nt":
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif proc.poll() is None:
            proc.kill()
        proc.wait()
        reader.join(timeout=2)
        if not reader.is_alive():
            proc.stdout.close()
    return {"ok": proc.returncode == 0 and not timed_out, "returncode": proc.returncode,
            "output": chunks.decode("utf-8", errors="replace"), "truncated": overflow[0], "timed_out": timed_out}


class Tools:
    def __init__(self, workspace):
        self.judge = None
        self.knowledge = None
        self.root = Path(workspace).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("Workspace must be a directory")

    def path(self, value):
        if not value:
            raise ValueError("Empty path")
        raw = Path(value)
        if raw.is_absolute() or ".." in raw.parts:
            raise ValueError("Only workspace-relative paths without '..' are allowed")
        candidate = self.root / raw
        cursor = self.root
        for part in raw.parts:
            cursor = cursor / part
            if cursor.is_symlink() or getattr(cursor, "is_junction", lambda: False)():
                raise ValueError("Symlinks and junctions are not followed")
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self.root):
            raise ValueError("Path escapes workspace")
        if any(p in {".git", ".aeon", ".ssh", ".gnupg"} or p == ".env" or p.startswith(".env.") for p in raw.parts):
            raise ValueError("Private/control path is excluded")
        return candidate

    def read(self, path, limit=12000, strict=False):
        target = self.path(path)
        # O_NOFOLLOW pins the final file on Linux; resolve checks also reject parent links.
        fd = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 2_000_000:
                raise ValueError("Reads require a regular file under 2 MB")
            data = handle.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError("File grew beyond read limit")
        return {"ok": True, "path": path, "sha256": hashlib.sha256(data).hexdigest(),
                "text": data[:limit].decode("utf-8", errors="strict" if strict else "replace"), "truncated": len(data)>limit}

    def read_lines(self, path, start_line, end_line):
        document = self.read(path, limit=2_000_000, strict=True)
        lines = document['text'].splitlines(keepends=True)
        if start_line > len(lines):
            raise ValueError('Start line is beyond the end of the file')
        text = ''.join(lines[start_line-1:end_line])
        if len(text.encode()) > 16000:
            raise ValueError('Requested lines exceed 16000 bytes; request a smaller range')
        return {**document, 'text': text, 'start_line': start_line, 'end_line': min(end_line, len(lines)),
                'total_lines': len(lines), 'excerpt': True,
                'truncated': start_line > 1 or end_line < len(lines)}

    def _edit_data(self, args):
        document = self.read(args['path'], limit=2_000_000, strict=True)
        if document['sha256'] != args['expected_sha256']:
            raise ValueError('File changed or expected_sha256 is wrong; read it again')
        text, old = document['text'], args['old_text']
        start = text.find(old)
        if start < 0 or text.find(old, start+1) >= 0:
            raise ValueError('old_text must match exactly once; include more surrounding text')
        data = (text[:start]+args['new_text']+text[start+len(old):]).encode()
        if len(data) > 2_000_000:
            raise ValueError('Edited file would exceed 2 MB')
        return data, document['sha256']

    def files(self, path):
        directory = self.path(path)
        if not directory.is_dir():
            raise ValueError("Expected directory")
        results = []
        with os.scandir(directory) as entries:
            for entry in entries:
                if len(results) >= 200:
                    return {"ok": True, "entries": sorted(results), "truncated": True}
                try:
                    self.path(str(Path(entry.path).relative_to(self.root)))
                except ValueError:
                    continue
                results.append(entry.name + ("/" if entry.is_dir(follow_symlinks=False) else ""))
        return {"ok": True, "entries": sorted(results), "truncated": False}

    def desktop(self):
        response = bounded_process(["hyprctl", "-j", "clients"], limit=128000, timeout=5)
        if not response["ok"] or response["truncated"]:
            raise ValueError("Cannot obtain complete Hyprland window state")
        rows = json.loads(response["output"])
        windows = [{k: row.get(k) for k in ("address", "title", "class", "pid")} for row in rows]
        return {"ok": True, "windows": windows}

    def prepare(self, action):
        """Bind a mutation to the current observed target before approval."""
        validate_action(action)
        tool, args = action["tool"], action["args"]
        if tool == 'edit_file':
            _, sha = self._edit_data(args)
            return {'sha256': sha}
        if tool == "write_file":
            path = self.path(args["path"])
            actual = self.read(args["path"])["sha256"] if path.exists() else "missing"
            if actual != args["expected_sha256"]:
                raise ValueError("File changed or expected_sha256 is wrong; read it again")
            if not path.parent.is_dir():
                raise ValueError("Parent directory must already exist")
            return {"sha256": actual}
        if tool == "focus_window":
            matches = [w for w in self.desktop()["windows"] if w["title"] == args["title"]]
            if len(matches) != 1:
                raise ValueError("Window title must match exactly one observed window")
            if not re.fullmatch(r"0x[0-9a-fA-F]+", matches[0]["address"] or ""):
                raise ValueError("Invalid observed window address")
            return matches[0]
        return {}

    def execute(self, action, binding=None):
        validate_action(action)
        tool, args = action["tool"], action["args"]
        try:
            if tool == 'recall':
                if self.knowledge is None:
                    raise ValueError('No knowledge store attached')
                return self.knowledge.search(args['query'])
            if tool in {'evidence_search', 'verify_claim', 'review'}:
                from . import evidence
                function = evidence.search if tool == 'evidence_search' else getattr(evidence, tool)
                return function(self, **args, judge=self.judge)
            if tool not in READ_TOOLS and self.prepare(action) != (binding or {}):
                raise ValueError("Observed target changed after approval")
            if tool == "list_files":
                return self.files(args["path"])
            if tool == "read_file":
                return self.read(args["path"])
            if tool == 'read_lines':
                return self.read_lines(**args)
            if tool == "search":
                root = self.path(args["path"])
                matches, scanned = [], 0
                paths = [root] if root.is_file() else self._walk(root)
                for path in paths:
                    scanned += 1
                    if scanned > 200:
                        break
                    try:
                        rel = str(path.relative_to(self.root))
                        content = self.read(rel)
                        for number, line in enumerate(content["text"].splitlines(), 1):
                            if args["text"].casefold() in line.casefold():
                                matches.append({"path": rel, "line": number, "text": line[:300]})
                                if len(matches) >= 30:
                                    return {"ok": True, "matches": matches, "bounded": True}
                    except (OSError, ValueError):
                        continue
                return {"ok": True, "matches": matches, "bounded": True,
                        "scope": "At most 200 files, first 12000 bytes per file"}
            if tool == "git_status":
                return bounded_process(["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "status", "--short", "--branch"], self.root)
            if tool == "system_info":
                return {"ok": True, "os": platform.system(), "release": platform.release(),
                        "machine": platform.machine(), "cpu_count": os.cpu_count()}
            if tool == "desktop_state":
                return self.desktop()
            if tool in {"write_file", "edit_file"}:
                path = self.path(args["path"])
                data = self._edit_data(args)[0] if tool == 'edit_file' else args['content'].encode()
                previous_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
                with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
                    temp = Path(handle.name)
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    if self.prepare(action) != binding:
                        raise ValueError("File changed during write preparation")
                    temp.chmod(previous_mode)
                    os.replace(temp, path)
                finally:
                    temp.unlink(missing_ok=True)
                verified = self.read(args["path"])
                return {"ok": verified["sha256"] == hashlib.sha256(data).hexdigest(),
                        "path": args["path"], "sha256": verified["sha256"], "bytes": len(data)}
            if tool == "run_command":
                return bounded_process(args["argv"], self.root, timeout=30)
            if tool == "focus_window":
                response = bounded_process(["hyprctl", "dispatch", "focuswindow", "address:"+binding["address"]], timeout=5)
                active = bounded_process(["hyprctl", "-j", "activewindow"], timeout=5)
                verified = active["ok"] and json.loads(active["output"]).get("address") == binding["address"]
                return {"ok": response["ok"] and verified, "focused": binding["title"], "verified": verified}
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            return {"ok": False, "error": str(exc)}
        raise ValueError("Unimplemented tool")

    def _walk(self, root):
        for directory, dirs, files in os.walk(root, followlinks=False):
            allowed = []
            for name in dirs:
                try:
                    self.path(str((Path(directory)/name).relative_to(self.root)))
                    if name not in {"node_modules", "__pycache__", ".venv", "target"}:
                        allowed.append(name)
                except ValueError:
                    pass
            dirs[:] = allowed
            for name in files:
                yield Path(directory) / name
