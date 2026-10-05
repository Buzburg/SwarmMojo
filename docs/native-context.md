# Native Mojo memory context

ROMS now has an MCP tool, `memory_prepare_context`, that selects source-bearing lessons within a strict JSON character budget. Its selection algorithm runs in native Mojo on the Mojo server, with a matching Python implementation for the Python server and Windows.

The practical feature is a compact bundle of relevant lessons and failed-attempt warnings. It keeps the source, revision, expiry and submitted test evidence attached to each selected record. It also reports omissions, duplicates and an incomplete candidate pool so an agent can see the limits of its context.

This is a deliberate ROMS design, not a claim that memory tools or knapsack selection are new inventions.

## Use it

Restart the server and reconnect the MCP client. Call:

```json
{
  "project_id": "roms",
  "query": "timezone conversion",
  "max_chars": 6000,
  "revision": ""
}
```

Use these arguments with the `memory_prepare_context` tool. Choose the same project ID used to retain the lessons. Set `revision` to an exact version when advice depends on that version; empty means no revision filter.

The result is a JSON string with:

- `backend`: `mojo` or `python`, identifying the selector actually called.
- `records`: selected lessons and warnings, with sources and evidence.
- `warning_available` and `warning_included`: whether a failed attempt was found in the candidate pool and included.
- `omitted`, `duplicates_removed`, `pool_truncated`: limits of the returned bundle.
- `selection`: the versioned ranking/packing policy.

The 1,024–20,000-character budget covers this JSON string, not the surrounding MCP envelope or a model's token count. If a warning cannot fit, `warning_included` is false. Do not interpret a missing warning as proof there were no failures.

## Selection policy

1. Query the existing scoped recall API for at most 20 current records, with a 20,000-character candidate-pool limit. Candidate, expired, superseded and retracted lessons are excluded. Any recall truncation is reported.
2. Collapse exact duplicate summaries with the same outcome and revision. Different outcomes remain separate. This does not resolve semantic contradictions or merge evidence across sources.
3. Calculate each compact record's serialized size, including its evidence. Utility is `10000 // retrieval_rank`, using the existing keyword/recent ordering. This is a heuristic preference, not a truth or confidence score.
4. Reserve the highest-ranked failed-attempt warning that fits. Solve a bounded 0/1 knapsack problem for the remaining capacity, maximizing total rank utility. Equal scores prefer the earlier records. The reserved warning can reduce the total utility; that is intentional.
5. Return whole records in retrieval order. Nothing is truncated mid-evidence. Validate the final output size and selector contract before returning it.

The portable and native algorithms use the same deterministic tie rules. All-fit pools take an early return. The native kernel accepts at most 64 items and a 20,000-character capacity; the public tool currently supplies at most 20 items.

## What is native

`app_mojo/context_select.mojo` owns the integer scoring loop, budget optimization and backtracking. It imports no Python module and makes no Python callbacks. `app_mojo/context_bindings.mojo` converts inputs and outputs once per call. The existing Mojo server registers this function through `PythonModuleBuilder`.

SQLite retrieval, memory lifecycle, JSON formatting and FastMCP transport still run in Python. The whole server has not been rewritten in Mojo. This CPU implementation does not use CUDA, ROCm or GPU-specific code. Validation here covers x86-64 Linux/WSL, with the Python path tested on Windows; it does not certify every AMD/Intel/NVIDIA configuration.

The binding approach follows [Modular's Python interoperability documentation](https://docs.modular.com/mojo/manual/python/mojo-from-python/); actual compilation was checked with the installed Mojo 1.1.0 toolchain.

## Measured results

The checked-in [benchmark result](native-context-benchmark.json) records nine samples per case, using Python 3.12.14 and Mojo 1.1.0 on the same x86-64 WSL environment. Medians include input/output conversion for native calls.

| Workload | Python | Mojo | Python time / Mojo time |
| --- | ---: | ---: | ---: |
| 5 records, all fit | 0.001401 ms | 0.003327 ms | 0.42× |
| 20 records, tight budget | 0.126287 ms | 0.013083 ms | 9.65× |
| 20 records, standard budget | 3.657080 ms | 0.142021 ms | 25.75× |
| 20 records, large budget | 16.929692 ms | 0.636624 ms | 26.59× |
| Context preparation with SQLite and JSON, 20 records | 8.386957 ms | 1.951127 ms | 4.30× |

Python was faster for the tiny all-fit case. These are local synthetic measurements, with warm caches and a small sample count. The last row includes recall, selection and serialization, but excludes MCP transport, model inference and startup. It is not a whole-agent speedup. No improvement in repair success rate or Kaggle score has been measured.

## Reproduce

In a fully installed Linux/WSL project environment:

```sh
pixi run bench-context
```

That runs 400 seeded Python/native parity cases, five invalid native inputs and the benchmark. The Python regression suite additionally checks 150 small packing instances against exhaustive search. The compiled-server MCP test exercises packing with a tight budget and verifies that the failure warning survives.

For offline Python regression tests:

```sh
python -m pytest tests/test_context.py tests/test_memory.py tests/test_release_safety.py -q
```

The standard `pixi run server` launch now includes the native selector. The Python `python -m app.server` launch uses the portable implementation. Both expose the same tool schema and record format, apart from the backend label. Existing project installation requirements still apply; compilation alone does not replace `pixi install`.

## Trust and scope

Evidence remains caller-supplied. Neither implementation executes a verification command or authenticates its receipt. Selected text is untrusted material for the agent to inspect. Packing does not activate skills, execute repairs, change stored memories or establish factual correctness.

The next product-level evaluation is a repair benchmark that compares the same agent with and without this context tool, measuring verified fixes, repeated mistakes, token use and total elapsed time. The current measurements establish a working native optimization, not that evaluation result.
