# Rule: meta-harness
<!-- Generated automatically by polyharness — DO NOT EDIT DIRECTLY -->

Guidelines for SwarmMojo MetaHarness and Coding Agent (Pi Tools + Prime Recursion)

**Applicable Paths**: `app/meta/**/*.py`

## Specific Guidelines
- Support heterogeneous local and remote models (Ollama, LM Studio, vLLM, SGLang, mock)
- Enforce bounded memory preambles and safe sandbox execution with Rewind checkpoints
- Maintain progressive task delegation between coordinators and specialist agents
- Use Pi exact unique match editing (edit_file_exact) with strict whitespace matching
- Use Prime recursive subagent delegation with strict max_depth limits and context isolation