"""Small TOML configuration with explicit per-model endpoints."""

import copy
import os
from pathlib import Path
import tomllib


def state_home():
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "aeon"


def config_path():
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "aeon/config.toml"


def load(path=None):
    defaults = Path(__file__).with_name("defaults.toml")
    config = tomllib.loads(defaults.read_text(encoding="utf-8"))
    target = Path(path) if path else config_path()
    if path and not target.is_file():
        raise ValueError(f"Config not found: {target}")
    if target.is_file():
        def merge(dst, src):
            for key, value in src.items():
                if isinstance(value, dict) and isinstance(dst.get(key), dict):
                    merge(dst[key], value)
                else:
                    dst[key] = copy.deepcopy(value)
        merge(config, tomllib.loads(target.read_text(encoding="utf-8")))
    for key in ("max_steps", "max_llm_calls", "max_context_bytes", "max_output_tokens", "timeout_seconds", "recipe_ttl_seconds"):
        value = config["harness"][key]
        if type(value) is not int or value <= 0:
            raise ValueError(f"harness.{key} must be a positive integer")
    if config["harness"]["model"] not in config["models"]:
        raise ValueError("Default model is not configured")
    decision = config['decisions']
    if type(decision['enabled']) is not bool or decision['routing'] not in {'off', 'shadow', 'auto'}:
        raise ValueError('Invalid decision enable flag or routing mode')
    for key in ('max_calls', 'cache_seconds'):
        if type(decision[key]) is not int or not 1 <= decision[key] <= 3600:
            raise ValueError(f'decisions.{key} must be an integer from 1 to 3600')
    for key in ('threshold', 'margin'):
        if type(decision[key]) not in (int, float) or not 0 <= decision[key] <= 1:
            raise ValueError(f'decisions.{key} must be from 0 to 1')
    return config
