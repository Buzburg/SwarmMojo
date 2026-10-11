"""Multi-model router and provider client for Swarmojo MetaHarness.

Supports:
- Local endpoints: Ollama, LM Studio, vLLM, Deep Reasoner, RWKV-7
- Generic OpenAI-compatible endpoints (local or remote)
- Deterministic mock execution for offline testing and bounded evaluations
- Heterogeneous model routing: different agents can use different local models
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
import httpx


@dataclass
class ModelConfig:
    """Configuration for an LLM model backend."""
    model_id: str
    backend: str = "mock"  # "ollama", "lmstudio", "vllm", "rwkv", "openai_compatible", "mock"
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "local"
    temperature: float = 0.2
    max_tokens: int = 2048
    context_window: int = 32768
    timeout_seconds: float = 60.0
    headers: Dict[str, str] = field(default_factory=dict)
    extra_params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ModelConfig:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# Standard Default Model Profiles
DEFAULT_PROFILES: Dict[str, ModelConfig] = {
    "mock": ModelConfig(
        model_id="mock-deterministic",
        backend="mock",
        base_url="local://mock",
        temperature=0.0,
    ),
    "ollama-qwen-coder": ModelConfig(
        model_id="qwen2.5-coder:7b",
        backend="ollama",
        base_url="http://localhost:11434/v1",
        api_key="ollama",
    ),
    "ollama-deepseek-r1": ModelConfig(
        model_id="deepseek-r1:14b",
        backend="ollama",
        base_url="http://localhost:11434/v1",
        api_key="ollama",
    ),
    "ollama-llama3": ModelConfig(
        model_id="llama3.3:70b",
        backend="ollama",
        base_url="http://localhost:11434/v1",
        api_key="ollama",
    ),
    "lmstudio-local": ModelConfig(
        model_id="local-model",
        backend="lmstudio",
        base_url="http://localhost:1234/v1",
        api_key="lmstudio",
    ),
    "vllm-local": ModelConfig(
        model_id="default",
        backend="vllm",
        base_url="http://localhost:8000/v1",
        api_key="vllm",
    ),
    "deep-reasoner-local": ModelConfig(
        model_id="default",
        backend="openai_compatible",
        base_url="http://localhost:18084/v1",
        api_key="local",
    ),
    "rwkv-local": ModelConfig(
        model_id="rwkv7",
        backend="rwkv",
        base_url="http://localhost:8000/v1",
        api_key="rwkv",
    ),
}


class ModelRegistry:
    """Registry of available model configs for agents in the meta-harness."""

    def __init__(self):
        self._profiles: Dict[str, ModelConfig] = dict(DEFAULT_PROFILES)
        self._load_environment_overrides()

    def _load_environment_overrides(self) -> None:
        """Allow environment variables to configure default model backends."""
        default_url = os.environ.get("SWARMMOJO_LOCAL_LLM_URL")
        default_model = os.environ.get("SWARMMOJO_LOCAL_MODEL")
        if default_url and default_model:
            self._profiles["default-local"] = ModelConfig(
                model_id=default_model,
                backend="openai_compatible",
                base_url=default_url,
                api_key=os.environ.get("SWARMMOJO_LOCAL_API_KEY", "local"),
            )

    def register(self, profile_name: str, config: ModelConfig) -> None:
        self._profiles[profile_name] = config

    def get(self, profile_name: str) -> ModelConfig:
        if profile_name in self._profiles:
            return self._profiles[profile_name]
        # Return a mock config if profile not found
        return ModelConfig(model_id=profile_name, backend="mock")

    def list_profiles(self) -> Dict[str, Dict[str, Any]]:
        return {name: cfg.to_dict() for name, cfg in self._profiles.items()}


class ModelClient:
    """Executes completions across local or remote model backends with fallback."""

    def __init__(self, registry: Optional[ModelRegistry] = None):
        self.registry = registry or ModelRegistry()

    def generate(
        self,
        config: ModelConfig,
        messages: List[Dict[str, str]],
        tools_schema: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Synchronously generate a completion from the configured model backend."""
        start = time.perf_counter()

        if config.backend == "mock":
            return self._mock_completion(config, messages, start)

        # Attempt call to local / remote OpenAI-compatible endpoint
        try:
            return self._call_openai_compatible(config, messages, tools_schema, start)
        except Exception as e:
            # If local service is offline or unreachable, fall back gracefully to deterministic completion
            fallback_res = self._mock_completion(config, messages, start)
            fallback_res["warning"] = f"Local endpoint {config.base_url} unreachable ({str(e)}). Returned deterministic fallback."
            return fallback_res

    def _call_openai_compatible(
        self,
        config: ModelConfig,
        messages: List[Dict[str, str]],
        tools_schema: Optional[List[Dict[str, Any]]],
        start_time: float,
    ) -> Dict[str, Any]:
        url = config.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
            **config.headers,
        }
        payload: Dict[str, Any] = {
            "model": config.model_id,
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            **config.extra_params,
        }
        if tools_schema:
            payload["tools"] = tools_schema
            payload["tool_choice"] = "auto"

        with httpx.Client(timeout=config.timeout_seconds) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        msg = choice.get("message", {})
        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return {
            "content": msg.get("content", ""),
            "tool_calls": msg.get("tool_calls", []),
            "model": config.model_id,
            "backend": config.backend,
            "latency_ms": round(latency_ms, 2),
            "usage": data.get("usage", {}),
            "finish_reason": choice.get("finish_reason", "stop"),
        }

    def _mock_completion(
        self,
        config: ModelConfig,
        messages: List[Dict[str, str]],
        start_time: float,
    ) -> Dict[str, Any]:
        last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        system_msg = next((m["content"] for m in messages if m.get("role") == "system"), "")

        # Synthesize role-grounded answer based on system prompt and task
        content = f"[Response from {config.model_id}] Received task: {last_user[:160]}"
        if "Architect" in system_msg:
            content = f"### Architecture Plan\n1. Analyze requirements for: {last_user}\n2. Identify modular components and invariants.\n3. Execute changes through isolated sandbox."
        elif "Reviewer" in system_msg:
            content = f"### Code Review Assessment\n- Verified correctness: Approved.\n- Security audit: No secrets or path traversal risks detected.\n- Test readiness: Pass."
        elif "Researcher" in system_msg:
            content = f"### Research Findings\n- Retrieved relevant knowledge and symbols for: {last_user}\n- Grounded context ready."
        elif "Coordinator" in system_msg:
            content = f"### Coordination Strategy\n1. Subtask A: Decomposed primary objective.\n2. Subtask B: Assigned to specialist agents.\n3. Synthesis: Ready for operator verification."

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        return {
            "content": content,
            "tool_calls": [],
            "model": config.model_id,
            "backend": "mock",
            "latency_ms": round(latency_ms, 2),
            "usage": {"prompt_tokens": len(last_user) // 4, "completion_tokens": len(content) // 4},
            "finish_reason": "stop",
        }
