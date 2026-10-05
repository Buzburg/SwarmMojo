# Security and release boundaries

ROMS is an experimental local tool for a single trusted operator. The installed Omarchy gateway requires a private bearer key; this does not provide tenant isolation or authorize arbitrary tool execution. Keep the gateway bound to loopback and use trusted MCP clients. A local MCP client can invoke tools that read documents and change records.

- Python plugins in `custom_tools/` execute with the server's filesystem permissions, including during hot reload. Review every plugin before installing it. The plugin folder is not a sandbox.
- Skills and retrieved text are untrusted input to an agent. Grounding prompts do not prevent prompt injection or guarantee correct actions.
- Container execution is disabled unless `ROMS_ENABLE_EXPERIMENTAL_EXECUTION=1` is explicitly set. The replacement worker lifecycle requires rootless Podman and a preinstalled local image; it never falls back to host execution or pulls an image during a task. Real tests cover timeout, repeated cancellation, process death, queue capacity and cleanup retry. Network access is fixed off, capabilities are dropped, privilege escalation is disabled, and CPU/memory/process/output/time limits apply. The broader native sandbox, broker authorization and staging/apply boundaries remain unfinished; this is not a certified hostile-code boundary. Installed service execution remains disabled.
- A failed worker cleanup retains its private task directory and `container.json` journal. The folder is removed only after owned containers are absent and the client process is reaped. `scripts/cleanup_worker.py TASK_ID` retries container removal; it preserves retained files for inspection. Worktree-removal failures are also retained and reported. Forced host termination/crash recovery still needs automatic reconciliation.
- Skill and knowledge names are restricted to simple filenames. This does not protect against a malicious local process racing filesystem changes.
- Memory project IDs filter records but do not authenticate clients. A trusted client can choose any project ID. Verification evidence is caller-supplied; the memory tools do not execute tests or authenticate results. Retrieved memory is untrusted content.
- Generated skills default to inactive drafts. Existing `add_skill` and explicit Python destination overrides remain privileged authoring paths requiring operator review.
- Forgetting a memory removes that record from application queries, not backups or recoverable SQLite pages.
- Lessons, evidence references, trajectories, support tickets and generated research can contain private data. Keep `data/`, environment files, databases, generated datasets and credentials out of Git. Review knowledge, skills and custom tools individually before publishing.
- Remote embedding configurations send document/query text to that endpoint. The default local model may need a first-use download.
- Dependency vulnerability auditing, a clean-machine installation and Mojo compilation are separate release checks; passing regression tests does not substitute for them.

Report suspected security issues privately to the repository owner. Do not include secrets or private documents in public issues.
