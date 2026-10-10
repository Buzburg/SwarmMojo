"""
mojo-agent-rewind — Python Bridge & CLI
Snapshot state fingerprinting and microsecond file rollback.
"""

import os
import sys
import json
import time
import shutil
import argparse
import subprocess

SNAPSHOT_DIR = ".mojo_rewind"
BLOBS_DIR = os.path.join(SNAPSHOT_DIR, "blobs")
MANIFEST_FILE = os.path.join(SNAPSHOT_DIR, "manifest.json")

IGNORED_DIRS = {".git", ".mojo_rewind", "node_modules", "target", "__pycache__", ".build-venv"}

def fnv1a_hash(data: bytes) -> int:
    h = 14695981039346656037
    for b in data:
        h = ((h ^ b) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h

class RewindEngine:
    def __init__(self, root: str = "."):
        self.root = os.path.abspath(root)
        self.snapshot_dir = os.path.join(self.root, SNAPSHOT_DIR)
        self.blobs_dir = os.path.join(self.root, BLOBS_DIR)
        self.manifest_file = os.path.join(self.root, MANIFEST_FILE)

    def init(self):
        os.makedirs(self.blobs_dir, exist_ok=True)
        if not os.path.exists(self.manifest_file):
            with open(self.manifest_file, "w", encoding="utf-8") as f:
                json.dump({"checkpoints": []}, f, indent=2)

    def load_manifest(self):
        self.init()
        with open(self.manifest_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_manifest(self, data):
        with open(self.manifest_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def scan_files(self):
        self.init()
        files_map = {}
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
            for fn in filenames:
                full_path = os.path.join(dirpath, fn)
                rel_path = os.path.relpath(full_path, self.root).replace("\\", "/")
                with open(full_path, "rb") as f:
                    content = f.read()
                h = hex(fnv1a_hash(content))[2:]
                blob_path = os.path.join(self.blobs_dir, h)
                if not os.path.exists(blob_path):
                    with open(blob_path, "wb") as bf:
                        bf.write(content)
                files_map[rel_path] = {"hash": h, "size": len(content)}
        return files_map

    def save_checkpoint(self, message: str = "Manual checkpoint"):
        start = time.perf_counter()
        files = self.scan_files()
        manifest = self.load_manifest()

        cp_id = f"cp-{len(manifest['checkpoints']) + 1}-{int(time.time())}"
        checkpoint = {
            "id": cp_id,
            "timestamp": time.time(),
            "message": message,
            "files": files
        }
        manifest["checkpoints"].append(checkpoint)
        self.save_manifest(manifest)
        duration_ms = (time.perf_counter() - start) * 1000.0

        return checkpoint, duration_ms

    def get_checkpoint(self, cp_id: str):
        checkpoints = self.load_manifest()["checkpoints"]
        if cp_id == "latest":
            return checkpoints[-1] if checkpoints else None
        checkpoint = next((c for c in checkpoints if c["id"] == cp_id), None)
        if checkpoint is None:
            raise ValueError(f"Unknown checkpoint: {cp_id}")
        return checkpoint

    def diff_checkpoint(self, cp_id: str):
        cp = self.get_checkpoint(cp_id)
        if not cp:
            return None

        current = self.scan_files()
        old_files = cp["files"]

        all_paths = sorted(set(current.keys()) | set(old_files.keys()))
        deltas = []

        for p in all_paths:
            if p not in old_files:
                deltas.append({"path": p, "change": "ADDED"})
            elif p not in current:
                deltas.append({"path": p, "change": "DELETED"})
            elif current[p]["hash"] != old_files[p]["hash"]:
                deltas.append({"path": p, "change": "MODIFIED"})

        return {"checkpoint": cp["id"], "deltas": deltas}

    def restore_checkpoint(self, cp_id: str):
        cp = self.get_checkpoint(cp_id)
        if not cp:
            return False

        current = self.scan_files()
        old_files = cp["files"]

        # Delete added files
        for p in current:
            if p not in old_files:
                os.remove(os.path.join(self.root, p))

        # Restore modified / deleted files
        for p, meta in old_files.items():
            full_path = os.path.join(self.root, p)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            blob_path = os.path.join(self.blobs_dir, meta["hash"])
            shutil.copyfile(blob_path, full_path)

        return True

    def snapshot(self, message: str = "checkpoint") -> dict:
        checkpoint, duration_ms = self.save_checkpoint(message=message)
        return {
            "checkpoint": checkpoint["id"],
            "timestamp": checkpoint["timestamp"],
            "message": checkpoint["message"],
            "file_count": len(checkpoint["files"]),
            "duration_ms": round(duration_ms, 2)
        }

    def rollback(self, checkpoint_index: int = -1, cp_id: str = None) -> dict:
        manifest = self.load_manifest()
        checkpoints = manifest.get("checkpoints", [])
        if not checkpoints:
            return {"success": False, "error": "No checkpoints available"}
        if cp_id:
            target_id = cp_id
        else:
            idx = checkpoint_index if checkpoint_index >= 0 else len(checkpoints) + checkpoint_index
            if 0 <= idx < len(checkpoints):
                target_id = checkpoints[idx]["id"]
            else:
                target_id = checkpoints[-1]["id"]
        success = self.restore_checkpoint(target_id)
        return {"success": success, "restored_checkpoint": target_id}


def main():
    parser = argparse.ArgumentParser(description="mojo-agent-rewind Time Machine")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init")
    save_p = subparsers.add_parser("save")
    save_p.add_argument("-m", "--message", default="Manual checkpoint")

    subparsers.add_parser("list")
    diff_p = subparsers.add_parser("diff")
    diff_p.add_argument("id", nargs="?", default="latest")

    restore_p = subparsers.add_parser("restore")
    restore_p.add_argument("id", nargs="?", default="latest")

    run_p = subparsers.add_parser("run")
    run_p.add_argument("cmd", nargs=argparse.REMAINDER)

    args = parser.parse_args()
    engine = RewindEngine()

    if args.command == "init":
        engine.init()
        print("✔ Initialized .mojo_rewind repository.")
    elif args.command == "save":
        cp, ms = engine.save_checkpoint(args.message)
        print(f"✔ Checkpoint '{cp['id']}' saved ({len(cp['files'])} files) in {ms:.2f} ms")
    elif args.command == "list":
        manifest = engine.load_manifest()
        print(f"Total checkpoints: {len(manifest['checkpoints'])}")
        for cp in manifest["checkpoints"]:
            print(f" - [{cp['id']}] {cp['message']} ({len(cp['files'])} files)")
    elif args.command == "diff":
        diff = engine.diff_checkpoint(args.id)
        if not diff:
            print("No checkpoints found.")
            return
        print(f"Diff against {diff['checkpoint']}:")
        for d in diff["deltas"]:
            print(f"  {d['change']:<8} {d['path']}")
    elif args.command == "restore":
        ok = engine.restore_checkpoint(args.id)
        if ok:
            print("✔ Workspace successfully restored!")
        else:
            print("Restore failed.")
    elif args.command == "run":
        if not args.cmd:
            print("Error: No command specified.")
            return
        cmd_str = " ".join(args.cmd)
        cp, _ = engine.save_checkpoint(f"Pre-run: {cmd_str}")
        print(f"► Checkpointed state before: '{cmd_str}'")
        res = subprocess.run(args.cmd)
        diff = engine.diff_checkpoint(cp["id"])
        if diff["deltas"]:
            print(f"⚠ {len(diff['deltas'])} file(s) modified. To undo: python rewind.py restore {cp['id']}")
    else:
        parser.print_help()

if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(2)
