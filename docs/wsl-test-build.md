# Custom Omarchy WSL test build

Built October 5, 2026. This is an Arch-based WSL variant using Omarchy 4.0.0 userland from the supplied ISO, Mojo socket transport, the existing ROMS memory service, and real RWKV-7 inference. It is an early working-system build, not completion of all 20 tasks in the pre-build plan.

## Use

From the project folder, open `Open Goose.cmd` for chat or `Open Omarchy.cmd` for the Linux shell. In the shell, run `goose`, `goose --status`, or `goose "your question"`. `/reset` clears the current CLI conversation; `/exit` closes it. The CLI retains only a bounded conversation window in memory. It does not claim recurrent checkpoint persistence across sessions.

WSL distribution name: `Omarchy`. Its filesystem is accessible through `\\wsl.localhost\Omarchy`. The original `\\wsl.localhost\Ubuntu` path is retired only after verified cutover; do not relabel Arch as Ubuntu simply to preserve that path.

## Add repositories and files

Open `Open Knowledge Library.cmd` in the project folder. Choose a file, local Git repository or folder, paste its Windows or Linux path, review the selection, and type `yes` to import. The same menu lists, refreshes and removes imported sources. Imports populate ROMS retrieval memory; they do not train or modify model weights, or execute imported code.

The Linux shell also provides `goose --library`. For scripting:

```sh
goose --add-file 'D:\path\document.md' --preview
goose --add-repo 'D:\path\repository' --preview
goose --add-folder 'D:\path\documents' --preview
goose --add-file 'D:\path\document.md'
goose --sources
goose --refresh-source SOURCE_ID
goose --remove-source SOURCE_ID
```

Remove `--preview` to perform an import. Git imports read tracked files from an existing local checkout, including working-copy edits. Untracked files are excluded; select them separately if needed. A folder import scans supported text files without applying Git ignore rules. No remote clone or credentials are required. Snapshots and manifests live in `~/.local/share/omarchy-harness/roms/library`. Document IDs include a unique source ID and relative path, so identical filenames in different sources remain independent. Removing an imported source deletes its indexed copy and snapshot, preserving original files. Refresh builds a new snapshot first and removes the previous source only after successful indexing; its source ID changes.

Supported inputs include Markdown, plain text, CSV, JSON, Python, Mojo, JavaScript/TypeScript, C/C++, Rust, Go and common text configuration formats. This increment does not import PDF, Office documents, images, archives or model weights. Limits are 1 MiB per file, 32 MiB and 1,000 eligible files per import, and 20,000 scanned entries for folders. Repository symlinks, generated directories, common credential filenames, `.env` names, binary/non-UTF-8 text and PEM private keys are excluded. These exclusions are not a comprehensive secret scanner; review the selected material before importing it.

Ordinary indexing errors remove that import's indexed documents and retain a failed manifest for inspection/removal. A forced interruption may leave an `indexing` source and partially indexed documents; remove or refresh that source from the menu. If cleanup fails, its manifest reports `cleanup_required`. Re-adding an existing origin creates another independent source; use refresh to replace it. Imports commit one document at a time, so concurrent queries may see an import in progress.

Verification: `scripts/check_source_intake.py` exercises the installed CLI with temporary repositories, real embeddings, same-name documents, cross-process cache refresh and removal. It removes its test sources afterward. The fixed verifier includes source-library and startup-readiness regressions; live readiness waits up to 90 seconds for a cold WSL start.

## Installed components

- Official Arch WSL base: `archlinux-2026.10.01.179549.wsl`, verified against the publisher's SHA-256.
- Custom package `omarchy-wsl 4.0.0-2`, repackaged from the user-supplied Omarchy ISO. Includes Omarchy commands, themes/configuration assets and shell integration. Native bootloader, disk layout, display manager, package-update hooks and full desktop integration are excluded from this WSL variant. This is a local custom package, not an official Omarchy WSL release. Native-oriented commands in the Omarchy command collection are not certified for WSL. Use Arch's package manager for this variant; do not run the native Omarchy full-system updater.
- Mojo broker compiled from current source. Native code retains peer-UID authentication, private socket directory, pinned path handling, framing and socket I/O. It now delegates bounded JSON/action handling to the existing Python environment rather than implementing a new parser in Mojo.
- Existing ROMS gateway and database, with a SQLite backup copy of the supplied `ROMS/data/roms.db`. The source database remains intact. Real embedding weights use MiniLM revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`; the safetensors file was verified against its published LFS digest.
- llama.cpp revision `46847e61582097979f539595d893d83d8e1d1af1`, built locally. For this increment the broker reaches inference through ROMS and the local server API. The proposed direct C adapter remains future work.
- Default model: supplied `rwkv7-g1g-2.9b-Q4_K_M.gguf`, using the tested `User:` / `Assistant:` template in `config/rwkv-user-assistant.jinja`, CPU backend, one inference slot, four CPU threads and a 4096-token configured window. The built-in `rwkv-world` template produced unrelated output and was replaced. Metadata stop-token warnings remain an evaluation item; a short smoke test is not comprehensive generation-quality certification.

The services are system-managed but execute as the unprivileged `rryan` user: `goose-model`, `goose-roms`, `omarchy-broker`. The broker socket is `/run/omarchy-broker/broker.sock`; systemd owns its private directory lifecycle. Model and gateway listen only on loopback, ports 18080 and 8844, with separate generated access keys. Keys are in `~/.config/goose/runtime.env` with private permissions. Do not paste this file into chat or commit it.

Application source remains in the Windows project folder, referenced by `/opt/omarchy-harness`. Runtime libraries are copied to `/opt/roms-env` for faster local imports. Model files remain in the project folder. Keep the project at its current path while using these services. Moving it requires updating the source link and model service path.

## Scope and known limits

Working goals for this increment are local chat, real memory retrieval, truthful readiness, current date/time, authenticated local APIs, native socket transport and restart recovery. Model output cannot execute commands. Experimental ROMS execution is explicitly disabled; broker sandbox integration and patch apply/rollback remain unfinished. No guest-provider credentials, web search, state checkpoint/fork API, autonomous repair or training are enabled.

The actual Mojo Landlock policy and its combination with rootless containers now pass enforcement tests. A locally built Python worker image supports registered syntax and unittest validation without a model-selected shell or image. See [native sandbox evidence](native-sandbox-verification.md). These components are not yet an assistant-accessible execution path.

The rootless worker lifecycle is now verified separately: timeout and cancellation stop/reap owned containers before temporary folders are removed; cleanup failures retain recoverable journals. `goose --cleanup-worker task_ID` retries removal of a retained worker's containers and preserves its files. The installed service keeps execution disabled pending the remaining sandbox/authorization gates. See [worker lifecycle evidence](worker-lifecycle-verification.md).

The 7.2B Q8 model loaded on this PC, but its CPU smoke test took about 108 seconds to become ready and generated about 2.9 tokens/second. The 2.9B smoke test took about 15 seconds to become ready and answered the arithmetic question correctly. Its approximately 14.5 tokens/second figure came from only three generated tokens, so it is not a representative benchmark. Actual gateway latency also includes retrieval and prompt processing.

This host is Ryzen 9 5980HX / 16 GB RAM, with WSL limited to 10 GB. It is not the future 128 GB target discussed in the PDF. Mesa exposes the Radeon RX 6800M through Direct3D12/Vulkan in the new system, but the installed inference build uses CPU and GPU inference is unverified.

The user has deferred 7.2B deployment and fine-tuning until the new computer. Keep both supplied models. Fine-tuning requires a suitable original training checkpoint and tokenizer plus reviewed training data; the quantized GGUF inference file is not itself a validated training setup. ROMS records are candidate evidence, not automatically approved training examples.

## Verification and maintenance

Use `scripts/verify_all.py` inside the selected Linux environment. It has a fixed test-build check list and fails for missing required binaries or tools. It no longer treats demo output or downloader dry-run as proof of inference/sandbox correctness. It does not certify excluded features.

For service diagnostics, inspect `systemctl status goose-model goose-roms omarchy-broker` and relevant journal entries. Restart through systemd, not by deleting socket paths. Source edits become visible immediately; recompile native code and rerun focused tests before restarting the broker. The installed native environment has its own broker binary and must be updated explicitly after a rebuild.

The default account is `rryan`; no new password was invented or configured. For administrative maintenance, open a root shell from Windows with `wsl -d Omarchy -u root`. The local-reference prompt permits general reasoning for ordinary questions; retrieved snippets constrain relevant local claims rather than forcing every question into the knowledge base.

## Recovery

The Ubuntu export is stored in the workspace at `deployment/backups/Ubuntu-before-Omarchy-20261005.tar`; its measured checksum is in the adjacent `.sha256.json` file. Recovery can import it under a new distribution name and a new directory with `wsl --import`. Do not import over the live Omarchy directory. The cutover verification record in the workspace states whether recovery import/boot and removal actually completed.

Upstream references: [Arch WSL downloads](https://geo.mirror.pkgbuild.com/wsl/2026.10.01.179549/), [Microsoft WSL import/export](https://learn.microsoft.com/en-us/windows/wsl/basic-commands), and [WSL GUI limitations](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gui-apps). WSL supports Linux GUI applications but does not provide the full native desktop environment described by the Omarchy ISO.
