# Omarchy Mojo RWKV7 Harness: Deployment & Download Readiness Guide

**Status:** Historical prototype notes. The production-readiness and milestone-completion claims in this document were not supported by the review. Use `docs/wsl-test-build.md` for the current test build and `../Omarchy Mojo Review.md` in the parent workspace for the defects. Sandbox enforcement, transactions and full desktop integration are unfinished; execution remains disabled.
**Current target:** Custom Arch/Omarchy WSL test build on Ryzen 9 5980HX / 16 GB RAM, using supplied Goose 2.9B. The later 7.2B/new-computer deployment and fine-tuning remain separate work. The sections below describe the old prototype and must not be treated as current acceptance evidence.

---

## 1. What Has Been Built & Verified

### 1. Native Mojo IPC Broker (`app_mojo/omarchy_broker.mojo`)
- Compiled Linux ELF binary: `.pixi/envs/default/bin/omarchy-broker`.
- Listens on `/run/omarchy/broker.sock` or `$OMARCHY_BROKER_SOCKET`.
- Enforces Linux `SO_PEERCRED` caller UID matching, umask 077, and directory pinning via `openat`/`procfs` to block symlink redirection.
- Supports both **Protocol v0** (`PING`, `STATUS`, `MOCK`, `ANCHOR`) and **Protocol v1** structured JSON framing (`{"v":1,"action":"ping"}`, `{"v":1,"action":"status"}`, `{"v":1,"action":"anchor"}`, `{"v":1,"action":"sandbox_status"}`, `{"v":1,"action":"landlock_probe"}`, `{"v":1,"action":"rwkv_status"}`).
- **Passed 21 real-process socket tests** in `tests/test_omarchy_broker.py`.

### 2. Native Landlock Filesystem Sandbox (`app_mojo/staging_sandbox.mojo`)
- Compiled Linux ELF binary: `.pixi/envs/default/bin/staging-sandbox`.
- Probes and utilizes Linux Landlock kernel subsystem (ABI version 1 verified on host kernel).
- Confines filesystem mutations: read-only access to `/`, write access strictly confined to isolated staging workspaces (`/tmp/omarchy-staging`).
- **Passed 4 unit tests** in `tests/test_staging_sandbox.py` verifying that unauthorized writes outside the sandbox are actively blocked by the kernel with `EACCES / PermissionError`.

### 3. RWKV-7 Recurrent State Lifecycle Engine (`app_mojo/rwkv_engine.mojo`)
- Compiled Linux ELF binary: `.pixi/envs/default/bin/rwkv-engine`.
- Manages continuous in-memory recurrent state buffers ($S_t$).
- Implements atomic disk serialization (`.tmp` write + POSIX rename) and sub-2ms cold restore.
- Implements in-memory state forking (`clone_state` via `memcpy`) allowing speculative dry-run patch testing without state pollution.
- Injects dynamic temporal anchoring (`[SYSTEM_ANCHOR] Year is 2026`) and anti-hallucination search envelopes.

### 4. ROMS RAG & Local Memory Integration
- Python MCP server, SQLite FTS5 rank fusion, OKF knowledge loader, and 8 project lesson memory tools.
- **114 passed tests** across release safety, memory lifecycle, context packing, and retrieval quality.

---

## 2. When You Wake Up: Ready-to-Run Next Steps

### Step 1: Download RWKV-7 Model Weights
Run the turnkey downloader script:
```bash
# In WSL or Linux from the ROMS folder:
pixi run python scripts/download_rwkv7.py --model 7.2b-q8
```
*Options:*
- `7.2b-q8` *(Recommended for Minisforum 128GB unified RAM)*: ~8.2 GB VRAM footprint, full FP16/Int8 precision, 60–85 tok/s.
- `7.2b-q4`: ~4.5 GB VRAM footprint, 90–130 tok/s.
- `2.9b`: ~1.6 GB VRAM footprint.
- `1.5b`: ~850 MB VRAM footprint.

To build `librwkv.so` with native AVX2 acceleration:
```bash
pixi run python scripts/download_rwkv7.py --build-librwkv
```

### Step 2: Deploy to Omarchy / Arch Linux
Run the turnkey Omarchy deployment installer:
```bash
bash scripts/setup_omarchy.sh
```
This automatically:
1. Verifies and compiles `.pixi/envs/default/bin/omarchy-broker`.
2. Creates `$XDG_RUNTIME_DIR/omarchy` with secure permissions (`0700`).
3. Installs `~/.local/bin/omarchy-harness` CLI wrapper.
4. Generates and registers `~/.config/systemd/user/omarchy-broker.service`.

To activate the broker daemon as a resident systemd service on your desktop:
```bash
systemctl --user daemon-reload
systemctl --user enable --now omarchy-broker
systemctl --user status omarchy-broker
```

### Step 3: Test the CLI Gateway
```bash
# Basic health ping
omarchy-harness PING

# Structured status check
omarchy-harness '{"v":1,"action":"status"}'

# Query temporal anchor
omarchy-harness '{"v":1,"action":"anchor"}'

# Check Landlock sandbox status
omarchy-harness '{"v":1,"action":"sandbox_status"}'
```

---

## 3. Verification Commands Reference

```bash
# Run the complete master verification suite (6/6 suites):
pixi run verify-all

# Run individual test suites:
pixi run test-broker      # 21 native socket tests
pixi run test-sandbox     # 4 Landlock and dryrun staging tests
```
