# Mojo bridge fix — September 27, 2026

## Result

The Mojo 1.1.0 server compiles and successfully serves actual MCP requests in WSL. The original compile failure is resolved. The build uses the existing project-local compiler; no alternate Python-only server replaced the Mojo handlers.

## Changes

- Bind five Mojo handlers using `PythonModuleBuilder.def_function`, with explicit PythonObject arguments and results. The wrappers call the original Mojo search and ticket functions.
- Register typed MCP schemas in `app/mojo_bridge.py`. This replaces passing raw Mojo function references and trying to evaluate a Python function definition as an expression.
- Construct Python `None` at runtime at the entry-point calls instead of asking the compiler to evaluate a Python runtime object as a default argument.
- Share the configured data/knowledge/skills paths with the Python components and initialize the supplemental Python schema used by tool discovery and trajectories.
- Send startup messages to stderr and propagate entry-point exceptions to a nonzero process exit.
- Change the existing seven-check Mojo runner to raise on failed assertions and isolate its database in a temporary directory.
- Anchor Windows/WSL and Linux launchers to this project and use its Pixi tasks. Both scripts pass syntax checks. A complete `pixi install` remains necessary; the existing checked-in environment folder was missing runtime dependencies.

The binding API is documented by [Modular's PythonModuleBuilder reference](https://docs.modular.com/mojo/std/python/bindings/PythonModuleBuilder/).

## Verified

1. Compile `app_mojo/main.mojo` using Mojo 1.1.0: passed.
2. Compile `app_mojo/test_roms.mojo`: passed.
3. Start the compiled server using the MCP Python SDK over stdio: successful initialize and tool listing.
4. Create, read, update and list a ticket through the actual Mojo callbacks: passed. Missing-ticket response: passed.
5. Search an isolated database containing a known vector/query pair: retrieved the expected source passage through the Mojo search callback.
6. Read `skills://customer_service` and request `customer_service_sop`: passed.
7. Reject a search limit of zero as an MCP tool error: passed.
8. Force startup failure with an invalid database path: nonzero exit, clean stdout.

The protocol test is `tests/test_mojo_protocol.py`. Its records are temporary; it does not require a model download. Retrieval uses a seeded vector and cached query embedding, so this validates transport, the native callback and database retrieval—not embedding-model quality. The complete seven-check model-dependent Mojo suite was compiled but not executed in this follow-up. Do not describe its seven checks as passed.

The local compiler emitted a Crashpad diagnostic about an unavailable crash reporter; compilation still completed successfully. Initial compilation also required MODULAR_HOME from the installed toolchain's environment. Missing Linux Python dependencies were installed into an isolated review directory for verification; existing user databases and the main Windows environment were preserved.

## Reproduce in Linux or WSL

From the ROMS folder, with Pixi installed:

```bash
pixi install
pixi run mojo build -I . app_mojo/main.mojo -o /tmp/roms-mojo
pixi run env PYTHONPATH=. python tests/test_mojo_protocol.py /tmp/roms-mojo "$PWD"
pixi run test
```

The last command uses the real embedding model and may download it on first use. The protocol test before it does not. Start the MCP server with `bash run_mojo.sh`; on Windows use `./run_mojo.ps1` after installing Pixi inside WSL. Supply `--test` to the shell launcher or `-Test` to the PowerShell launcher to run the model-dependent suite. The launchers propagate failure status instead of reporting success after an error.

## Remaining scope

This fixes the Mojo bridge and its verified tool path. It does not establish full Python/Mojo feature parity, concurrency safety, live inference-backend integration, container sandbox safety or measured retrieval accuracy. Keep the developer-preview label and the security boundaries in SECURITY.md.

Original modified files are backed up separately in the review output under `before-mojo-fix/`. The GitHub preview archive and file manifest were refreshed after this fix. Nothing was pushed to GitHub.
