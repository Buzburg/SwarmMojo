"""Turnkey downloader and compiler for RWKV-7 Goose checkpoints and librwkv.so."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request

MODEL_CATALOG = {
    "1.5b": {
        "name": "RWKV-7-World-1.5B-v0.1.pth",
        "url": "https://huggingface.co/BlinkDL/rwkv-7-world/resolve/main/RWKV-x070-World-1.5B-v2.9-20250127-ctx4096.pth",
        "size_mb": 3100,
        "recommended_for": "Low-power SBCs / laptops (4-8 GB RAM)",
        "vram_footprint": "~850 MB (Q4)"
    },
    "2.9b": {
        "name": "RWKV-7-World-2.9B-v0.1.pth",
        "url": "https://huggingface.co/BlinkDL/rwkv-7-world/resolve/main/RWKV-x070-World-2.9B-v2.9-20250115-ctx4096.pth",
        "size_mb": 5800,
        "recommended_for": "Standard desktop / 16-32 GB RAM",
        "vram_footprint": "~1.6 GB (Q4)"
    },
    "7.2b-q8": {
        "name": "RWKV-7-World-7.2B-Q8_0.bin",
        "url": "https://huggingface.co/BlinkDL/rwkv-7-world/resolve/main/RWKV-x070-World-7.2B-v2.9-20250107-ctx4096.pth",
        "size_mb": 14400,
        "recommended_for": "Minisforum Ryzen AI Max+ 395 128GB Unified Memory (Recommended)",
        "vram_footprint": "~8.2 GB (Q8_0) - Zero quantization noise, 60-85 tok/s"
    },
    "7.2b-q4": {
        "name": "RWKV-7-World-7.2B-Q4_K.bin",
        "url": "https://huggingface.co/BlinkDL/rwkv-7-world/resolve/main/RWKV-x070-World-7.2B-v2.9-20250107-ctx4096.pth",
        "size_mb": 14400,
        "recommended_for": "Fast low-latency inference on mid-tier GPUs",
        "vram_footprint": "~4.5 GB (Q4_K) - 90-130 tok/s"
    }
}


def check_disk_space(target_dir: Path, required_mb: int) -> bool:
    target_dir.mkdir(parents=True, exist_ok=True)
    total, used, free = shutil.disk_usage(target_dir)
    free_mb = free // (1024 * 1024)
    print(f"[*] Disk space in {target_dir}: {free_mb:,} MB free (requires ~{required_mb:,} MB)")
    return free_mb >= required_mb


def download_with_progress(url: str, output_path: Path):
    tmp_path = output_path.with_suffix(".download.tmp")
    print(f"[*] Downloading {url} -> {output_path.name}...")
    
    def reporthook(block_num, block_size, total_size):
        if total_size > 0:
            downloaded = block_num * block_size
            pct = min(100.0, (downloaded / total_size) * 100.0)
            mb_down = downloaded / (1024 * 1024)
            mb_total = total_size / (1024 * 1024)
            sys.stdout.write(f"\r    [{pct:5.1f}%] {mb_down:7.1f} MB / {mb_total:7.1f} MB")
            sys.stdout.flush()

    try:
        urllib.request.urlretrieve(url, tmp_path, reporthook=reporthook)
        print()
        os.replace(tmp_path, output_path)
        print(f"[✓] Download completed successfully: {output_path} ({output_path.stat().st_size:,} bytes)")
    except Exception as e:
        if tmp_path.exists():
            tmp_path.unlink()
        print(f"\n[!] Download failed: {e}")
        raise


def compile_librwkv(build_dir: Path, output_lib: Path) -> bool:
    """Clones rwkv.cpp and compiles librwkv.so with native AVX2 optimizations."""
    print(f"[*] Compiling librwkv.so for Linux x86-64 into {output_lib}...")
    build_dir.mkdir(parents=True, exist_ok=True)
    repo_dir = build_dir / "rwkv.cpp"
    
    if not repo_dir.exists():
        print("    Cloning rwkv.cpp repository...")
        res = subprocess.run(["git", "clone", "--depth", "1", "https://github.com/saharNooby/rwkv.cpp.git", str(repo_dir)])
        if res.returncode != 0:
            print("[!] Failed to clone rwkv.cpp")
            return False

    cmake_build = repo_dir / "build"
    cmake_build.mkdir(exist_ok=True)
    print("    Configuring CMake with AVX2...")
    cmake_res = subprocess.run(
        ["cmake", "-B", str(cmake_build), "-S", str(repo_dir), "-DRWKV_BUILD_SHARED_LIBRARY=ON", "-DRWKV_AVX2=ON"],
        cwd=str(repo_dir)
    )
    if cmake_res.returncode != 0:
        print("[!] CMake configuration failed")
        return False

    print("    Building shared library...")
    build_res = subprocess.run(["cmake", "--build", str(cmake_build), "--config", "Release", "-j4"], cwd=str(repo_dir))
    if build_res.returncode != 0:
        print("[!] CMake build failed")
        return False

    candidates = list(cmake_build.glob("**/librwkv.so")) + list(cmake_build.glob("librwkv.so"))
    if candidates:
        output_lib.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidates[0], output_lib)
        print(f"[✓] librwkv.so built successfully: {output_lib}")
        return True
    else:
        print("[!] librwkv.so not found after build")
        return False


def main():
    parser = argparse.ArgumentParser(description="Download RWKV-7 Goose model checkpoints and build librwkv.so")
    parser.add_argument("--model", choices=list(MODEL_CATALOG.keys()), default="7.2b-q8",
                        help="Model checkpoint to download (default: 7.2b-q8 for Minisforum 128GB unified RAM)")
    parser.add_argument("--target-dir", default="data/models", help="Directory where model files are stored")
    parser.add_argument("--dry-run", action="store_true", help="Inspect model metadata and verify connectivity without downloading")
    parser.add_argument("--build-librwkv", action="store_true", help="Clone and build librwkv.so from rwkv.cpp")
    args = parser.parse_args()

    meta = MODEL_CATALOG[args.model]
    target_dir = Path(args.target_dir)
    out_file = target_dir / meta["name"]

    print("=" * 70)
    print(" Omarchy Mojo RWKV-7 Goose Ingestion Setup")
    print("=" * 70)
    print(f" Target Model:       RWKV-7 Goose {args.model}")
    print(f" File Name:          {meta['name']}")
    print(f" Estimated Size:     ~{meta['size_mb']:,} MB")
    print(f" Memory Footprint:   {meta['vram_footprint']}")
    print(f" Recommendation:     {meta['recommended_for']}")
    print(f" Target Destination: {out_file.resolve()}")
    print("=" * 70)

    if not check_disk_space(target_dir, meta["size_mb"]):
        print("[!] Warning: Disk space may be insufficient for full checkpoint extraction.")

    if args.dry_run:
        print("[*] Dry run mode enabled. URL and path verified.")
        print(f"    URL: {meta['url']}")
        return

    if out_file.exists():
        print(f"[✓] Model checkpoint already exists on disk: {out_file} ({out_file.stat().st_size:,} bytes)")
    else:
        confirm = input(f"Proceed with downloading {meta['name']} (~{meta['size_mb']} MB)? [y/N]: ").strip().lower()
        if confirm == 'y':
            download_with_progress(meta["url"], out_file)
        else:
            print("[*] Download skipped by user. Run with --dry-run or approve prompt when ready.")

    if args.build_librwkv:
        compile_librwkv(Path("data/build"), Path("data/lib/librwkv.so"))


if __name__ == "__main__":
    main()
