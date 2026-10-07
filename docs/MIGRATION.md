# From ROMS to SwarmMojo

SwarmMojo starts from verified ROMS commit `2d2e207bf2a97c1370971a5e34dbe3bf80ab7348`. It is a separate repository. The original ROMS repository is private, and the older `Buzburg/swarm-mojo` project is also separate and unchanged by this migration.

Use `python swarmmojo.py` in place of `python roms.py`. Commands and arguments remain the same. MCP clients should launch `swarmmojo.py mcp`; the advertised server name is now **SwarmMojo**. The preferred preparation tool is `swarmmojo_prepare_harness`; `roms_prepare_harness` remains an alias with the same validation and approval boundary.

The new launcher accepts `SWARMMOJO_*` environment variables and maps them to the corresponding existing `ROMS_*` settings before loading the runtime. An explicit new setting wins when both are present. Explicit legacy settings still work. Without a configured state directory, the new launcher uses `~/.swarmmojo` for standalone decision-discovery state; the legacy launcher retains its old default. Repository-local data stays in this checkout's `data/` directory. No previous data is automatically moved or deleted.

Direct Python/module entry points and optional native/system services continue to use their documented `ROMS_*` configuration names. The new variable aliases apply through `swarmmojo.py`; they do not silently rename every environment variable in existing services.

Stable protocol IDs such as `roms.harness/v1`, existing `roms_*` MCP tools, module/class names, database formats and native binary names remain intact for compatibility. Historical reports retain their original names and measurement context. This is intentional; the public project identity is SwarmMojo. Existing approvals, evidence limits and Linux-only workshop requirements remain in force.

To reuse prior knowledge, explicitly point `SWARMMOJO_DB_PATH` at a chosen index or rebuild one using the existing ingestion tools. Do not configure simultaneous writers to a shared index without understanding the existing store's concurrency contract. Imported playbooks do not activate execution or authorize edits.

Current third-party additions and their exact revisions are recorded in [imported skills](IMPORTED-SKILLS.md). Other projects listed in the [upstream evaluation](UPSTREAM-EVALUATION.md) are research candidates unless explicitly labelled included.
