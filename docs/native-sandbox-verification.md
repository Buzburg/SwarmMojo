# Native sandbox and registered validation — October 5, 2026

The actual Mojo enforcement path now compiles and runs. Tests invoke that compiled code, independently test rootless-container isolation, and then exercise both layers together. The installed assistant still cannot execute commands: broker authorization, staged promotion and recovery integration remain unfinished.

## Native policy

`app_mojo/staging_sandbox.mojo` now uses a consistent variadic C `syscall` declaration returning `long`, checks ruleset/rule/restriction results, and requires Landlock ABI 3 or newer. ABI 7 was observed on this WSL kernel. The minimum includes `REFER` and `TRUNCATE`; ABI 5+ also handles device ioctl restrictions. Unsupported enforcement fails before the requested command executes. These rights follow the [kernel Landlock contract](https://docs.kernel.org/userspace-api/landlock.html); the FFI uses [Mojo's documented variadic call convention](https://mojolang.static.modular.com/docs/std/ffi/external_call/).

The staging root must be an existing absolute directory owned by the worker user with private permissions. Every component is opened using `openat` with no-follow directory flags. Rules and the working directory use the pinned descriptor. Symlink redirection cannot substitute another writable directory after it is pinned. Only `/usr` is readable/executable outside the stage. The launcher clears inherited environment variables, closes descriptors above stderr and replaces itself with the confined program. It grants no host-wide read rule and does not create a missing staging directory implicitly.

Compiled artifact: `/opt/roms-env/bin/staging-sandbox`.

SHA-256: `f37dc8b617af154a5d72771110cc46ffb9df736dec0c3c9f1ed4d03325cd26ef`.

## Combined worker image and command policy

`scripts/build_worker_image.py` packages the compiled launcher, the installed Arch Python 3.14 interpreter/stdlib and resolved runtime libraries into a scratch image. The build uses no network and copies no home directories or credentials. Its entrypoint is the Mojo launcher with `/workspace` as the required private stage. The selected image is immutable:

`sha256:7671ccac46e275350fd2d458f755880fb97518db6f117b9cb6ffc346f2bf672d`

The full 704-file digest manifest is `deployment/packages/worker-image.manifest.json` in the parent workspace. Machine-local image selection is generated in `config/worker-image.local.json` and excluded from Git. Rebuilding writes a new image selection and provenance manifest; verification must use the rebuilt image ID.

`app/validation_policy.py` registers two typed requests: `python.syntax` with 1–64 relative Python file paths, and `python.tests` with fixed unittest discovery in a real `tests` directory containing test files. Requests cannot select a shell, executable, image, network setting or arbitrary flags. Absolute/traversal/option paths, symlinks and oversized inputs are rejected. Effective arguments, immutable image, policy version and resource limits are recorded outside the writable stage before execution. Syntax and unittest failures retain their real nonzero exit status.

This registry is a building block for staged validation, not a new model-accessible execution endpoint. Trusted-operator legacy experimental helpers still exist behind their disabled opt-in flag. No proof here substitutes for approval of a proposed patch or certifies the correctness of arbitrary test code.

## Verification evidence

`scripts/verify_all.py --containers --sandbox` passed all five required groups:

| Group | Evidence |
|---|---|
| Python regression inventory | 142 passed |
| Compiled Mojo broker | 22 passed |
| Live model and ROMS | ready, model `goose-2.9b`, execution disabled |
| Rootless worker lifecycle and independent isolation | 9 passed |
| Native and combined sandbox | 13 passed |

The native suite contains 11 checks, including 14 denied operations in one test: outside read/create/truncate, both directions of rename/link, unlink/mkdir/rmdir, FIFO/symlink creation and symlink escape. Legitimate stage writes, truncation and cross-directory moves/links succeed. Other checks close an inherited writable descriptor, reject invalid/private/foreign/symlink paths, and repeatedly race directory replacement without an outside write.

The independent container check verifies no host secret environment value or container socket, no usable network interface except loopback, a read-only root, zero effective capabilities, no-new-privileges, a 64 MiB memory ceiling, 128-process limit and actual CPU cgroup quota. The combined tests prove the native policy runs inside the container, including denial of writes to its otherwise writable `/tmp`, and exercise passing/failing syntax and unittest validation. Final enumeration found no ROMS-owned containers.

The old Python-only Landlock test and dummy state-file test were removed as acceptance evidence. `scripts/test_landlock_sandbox.py` and `pixi run test-sandbox` now run `tests/test_native_sandbox.py` against a required compiled artifact. Missing selected images or binaries fail the explicit verifier groups rather than silently skipping them.

## Remaining work

The broker still needs a policy-aware worker launch path and a protected staged patch/apply/rollback lifecycle. The gateway's no-new-privileges setting remains intact; a dedicated user worker launch context is needed for integration. Crash reconciliation, image distribution/licensing inventory, broader toolchains and a clean-machine rebuild remain future gates. Native desktop, recurrent model checkpoint/fork, guest delegation and training are unaffected by this milestone.
