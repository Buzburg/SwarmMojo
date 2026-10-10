# Rule: meta-harness
<!-- Generated automatically by polyharness — DO NOT EDIT DIRECTLY -->

Guidelines for SwarmMojo MetaHarness multi-agent and multi-model execution

**Applicable Paths**: `app/meta/**/*.py`

## Specific Guidelines
- Support heterogeneous local and remote models (Ollama, LM Studio, vLLM, SGLang, mock)
- Enforce bounded memory preambles and safe sandbox execution with Rewind checkpoints
- Maintain progressive task delegation between coordinators and specialist agents