"""Bounded, real inference check; always stops the temporary server."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", type=Path)
    parser.add_argument("--port", type=int, default=18081)
    args = parser.parse_args()
    binary = Path.home() / ".local/share/omarchy-harness/llama.cpp/build-cpu/bin/llama-server"
    log = args.model.parent / "tmp" / (args.model.stem + "-smoke.log")
    started = time.monotonic()
    with log.open("w") as output:
        process = subprocess.Popen([str(binary), "-m", str(args.model), "--host", "127.0.0.1",
                                    "--port", str(args.port), "-c", "1024", "-np", "1",
                                    "-b", "64", "-ub", "64", "-t", "4", "-ngl", "0",
                                    "--no-warmup"], stdout=output, stderr=subprocess.STDOUT)
        try:
            base = f"http://127.0.0.1:{args.port}"
            while time.monotonic() - started < 120:
                if process.poll() is not None:
                    raise RuntimeError(f"Runtime exited {process.returncode}; inspect {log}")
                try:
                    with urllib.request.urlopen(base + "/health", timeout=2) as response:
                        if response.status == 200:
                            break
                except (OSError, urllib.error.URLError):
                    time.sleep(1)
            else:
                raise TimeoutError("Model not ready within 120 seconds")
            ready = time.monotonic() - started
            payload = {"prompt": "User: What is two plus two? Answer briefly.\n\nAssistant:",
                       "n_predict": 24, "temperature": 0, "seed": 42,
                       "stop": ["\n\nUser:"]}
            request = urllib.request.Request(base + "/completion", json.dumps(payload).encode(),
                                             {"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=120) as response:
                result = json.load(response)
            report = {"model": args.model.name, "ready_seconds": round(ready, 2),
                      "content": result.get("content"), "timings": result.get("timings"),
                      "backend": "CPU", "context": 1024}
            log.with_suffix(".json").write_text(json.dumps(report, indent=2))
            print(json.dumps(report, indent=2), flush=True)
            if not str(result.get("content", "")).strip():
                raise RuntimeError("Model produced no text")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


if __name__ == "__main__":
    main()
