"""Build the pinned GGUF runtime on Linux without installing a service."""
from pathlib import Path
import subprocess

REVISION = "46847e61582097979f539595d893d83d8e1d1af1"


def main() -> None:
    root = Path.home() / ".local/share/omarchy-harness/llama.cpp"
    root.parent.mkdir(parents=True, exist_ok=True)
    if not root.exists():
        subprocess.run(["git", "init", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "remote", "add", "origin",
                        "https://github.com/ggml-org/llama.cpp.git"], check=True)
    actual = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                            capture_output=True, text=True)
    if actual.stdout.strip() != REVISION:
        if subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"]):
            raise RuntimeError("Runtime source has local changes; refusing checkout")
        subprocess.run(["git", "-C", str(root), "fetch", "--depth=1", "origin", REVISION], check=True)
        subprocess.run(["git", "-C", str(root), "checkout", "--detach", REVISION], check=True)
    build = root / "build-cpu"
    subprocess.run(["cmake", "-S", str(root), "-B", str(build),
                    "-DCMAKE_BUILD_TYPE=Release", "-DGGML_VULKAN=OFF",
                    "-DLLAMA_CURL=OFF", "-DLLAMA_BUILD_TESTS=OFF"], check=True)
    subprocess.run(["cmake", "--build", str(build), "--target", "llama-server",
                    "llama-cli", "-j", "3"], check=True)
    print(f"Built pinned runtime {REVISION}: {build / 'bin'}", flush=True)


if __name__ == "__main__":
    main()
