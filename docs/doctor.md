# Goose readiness guide

Run `goose --doctor` inside the installed Omarchy environment. It explains the current broker status and gives concrete next steps. The existing `goose --status` remains the machine-readable JSON view.

The broker transport currently requires Linux, including Omarchy running inside WSL. Running doctor directly in native Windows or macOS reports unsupported transport with exit code 1, even if that Python exposes Unix sockets: the installed broker lives in the Linux environment. A Linux Python without Unix-socket support also reports this limitation. Doctor does not launch WSL or connect through an alternative transport automatically.

Doctor sends one `STATUS` request to the local broker, with a ten-second overall deadline and a 64 KiB response limit. The broker obtains its ordinary gateway/model health and validation-worker reachability. Doctor does not generate a model response, inspect private lessons, index files, run a sandbox validation, repair anything, or start/restart a service.

The report distinguishes model/service readiness from worker reachability and untested features. An idle native worker is configured, but this check does not certify a loaded native model. Workshop prerequisites do not certify sandbox enforcement or the correctness of a future draft. Missing and unknown states stay unreported; binary or file existence never establishes readiness. Broker conversation restore describes that public interface, not the separate experimental checkpoint tools.

Exit code 0 means the broker reports chat readiness and workshop prerequisites, with no native cleanup failure. Exit code 1 means those prerequisites are incomplete, native cleanup is required, or status could not be read safely. This is a scoped snapshot, not a release certification. Unavailable optional features do not by themselves cause a failure exit.

Doctor prints only fixed labels and advice. Raw broker reasons, model names, errors, paths, environment values and credentials are not printed. If requesting help, review any separately collected logs before sharing them.

After a cold start, services may need up to 90 seconds. Retry doctor after that interval if needed. If model or knowledge services stay unavailable, inspect `systemctl status goose-model goose-roms omarchy-broker --no-pager`. For an unavailable validation worker, inspect `systemctl --user status omarchy-task-worker --no-pager`. These suggestions inspect state; doctor does not execute them. Do not broaden socket permissions to work around access errors.

Focused verification: `python -m pytest tests/test_doctor.py -q` in the pinned Linux environment. Tests cover unavailable/degraded/malformed status, bounded reads and total deadlines, unsafe output suppression, command conflicts, and preservation of the JSON status view.

Before the portability changes, verified October 6, 2026: 30 focused tests passed in 0.44 seconds in Linux. Running the direct script against the installed broker returned exit code 0: model and knowledge service ready, validation worker reachable, native worker configured and idle. No model response or sandbox validation was requested. This historical snapshot does not certify the changed source, later service health or the full public release.

The portability correction guards missing `socket.AF_UNIX`, explicitly reports unsupported native hosts, isolates protocol tests from the host platform, and gives malformed-payload cases short test IDs. Four platform cases were added. After approval availability returned, verification passed: 34 doctor tests on Windows and 34 on Linux. The six-file Windows release run passed 127 tests with one host-restricted symlink test skipped. Logs and JUnit reports are in `review-artifacts/os-operator` in the parent workspace. These checks establish the tested readiness interface, not full desktop or hardware qualification.
