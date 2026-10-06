"""Build the pinned GGUF runtime on Linux without installing a service."""
from pathlib import Path
import json
import subprocess

INPUTS = json.loads((Path(__file__).resolve().parents[1] / 'config/build-inputs.json').read_text())
REVISION = INPUTS['runtime']['revision']
REPOSITORY = INPUTS['runtime']['repository']


def verify_clean_source(root: Path) -> None:
    if subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain']):
        raise RuntimeError('Runtime source has local changes; refusing to build or checkout')
    origin = subprocess.check_output(['git', '-C', str(root), 'remote', 'get-url', 'origin'], text=True).strip()
    if origin != REPOSITORY:
        raise RuntimeError('Runtime source origin does not match the pinned input record')


def main() -> None:
    root = Path.home() / ".local/share/omarchy-harness/llama.cpp"
    root.parent.mkdir(parents=True, exist_ok=True)
    if not root.exists():
        subprocess.run(["git", "init", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "remote", "add", "origin",
                        REPOSITORY], check=True)
    verify_clean_source(root)
    actual = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                            capture_output=True, text=True)
    if actual.stdout.strip() != REVISION:
        subprocess.run(["git", "-C", str(root), "fetch", "--depth=1", "origin", REVISION], check=True)
        subprocess.run(["git", "-C", str(root), "checkout", "--detach", REVISION], check=True)
    verified = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if verified != REVISION:
        raise RuntimeError('Runtime source revision does not match the pinned input record')
    verify_clean_source(root)
    build = root / "build-cpu"
    subprocess.run(["cmake", "-S", str(root), "-B", str(build),
                    "-DCMAKE_BUILD_TYPE=Release", "-DGGML_VULKAN=OFF",
                    "-DLLAMA_CURL=OFF", "-DLLAMA_BUILD_TESTS=OFF"], check=True)
    subprocess.run(["cmake", "--build", str(build), "--target", "llama-server",
                    "llama-cli", "-j", "3"], check=True)
    print(f"Built pinned runtime {REVISION}: {build / 'bin'}", flush=True)


if __name__ == "__main__":
    main()
