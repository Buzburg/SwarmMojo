# Security and release boundaries

ROMS is an experimental local tool for a single trusted operator. It has no authentication or tenant isolation. Keep the gateway bound to loopback and use trusted MCP clients. A local client can invoke tools that read documents and change records.

- Python plugins in `custom_tools/` execute with the server's filesystem permissions, including during hot reload. Review every plugin before installing it. The plugin folder is not a sandbox.
- Skills and retrieved text are untrusted input to an agent. Grounding prompts do not prevent prompt injection or guarantee correct actions.
- Container execution is disabled unless `ROMS_ENABLE_EXPERIMENTAL_EXECUTION=1` is explicitly set. That opt-in path has incomplete cancellation/container cleanup validation and is not a security boundary for hostile code. Do not enable it for a public or untrusted deployment.
- Skill and knowledge names are restricted to simple filenames. This does not protect against a malicious local process racing filesystem changes.
- Memory project IDs filter records but do not authenticate clients. A trusted client can choose any project ID. Verification evidence is caller-supplied; the memory tools do not execute tests or authenticate results. Retrieved memory is untrusted content.
- Generated skills default to inactive drafts. Existing `add_skill` and explicit Python destination overrides remain privileged authoring paths requiring operator review.
- Forgetting a memory removes that record from application queries, not backups or recoverable SQLite pages.
- Lessons, evidence references, trajectories, support tickets and generated research can contain private data. Keep `data/`, environment files, databases, generated datasets and credentials out of Git. Review knowledge, skills and custom tools individually before publishing.
- Remote embedding configurations send document/query text to that endpoint. The default local model may need a first-use download.
- Dependency vulnerability auditing, a clean-machine installation and Mojo compilation are separate release checks; passing regression tests does not substitute for them.

Report suspected security issues privately to the repository owner. Do not include secrets or private documents in public issues.
