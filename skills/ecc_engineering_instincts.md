---
name: ecc_engineering_instincts
title: ECC & LifeOS Sovereign Engineering Instincts
description: High-signal agent engineering habits, 7-step execution loop, and deterministic verification constraints synthesized from affaan-m/ECC and danielmiessler/LifeOS.
---

# ECC & LifeOS Sovereign Engineering Instincts

Directly synthesized from `affaan-m/ECC` (Everything Claude Code) and `danielmiessler/LifeOS`:
Apply these core engineering instincts to all Omarchy OS coding, debugging, and system administration tasks.

---

## 🛠️ The 7-Step Execution Loop (LifeOS Algorithm)

1. **Observe**: Read the exact source files, logs, and schema definitions before proposing any modification.
2. **Think**: Identify the root cause or architectural boundary; reject superficial symptom-masking fixes.
3. **Plan**: Formulate the smallest, safest verifiable slice that solves the problem.
4. **Build**: Write surgical, minimal diffs. Preserve all existing comments, docstrings, and unrelated formatting.
5. **Execute**: Stage the patch inside the isolated Landlock / Podman validation sandbox.
6. **Verify**: Run deterministic AST static checks (`ast_validator.py`) and automated test suites (`unittest` / `pytest`).
7. **Learn**: Record the outcome via `ContinuousMemoryReflector` (`reflection.py`) so future turns inherit verified knowledge.

---

## 🔒 Zero-Trust & Quality Constraints

- **Deterministic Enforcement Outside the Model**: Never rely on prompt wording alone to prevent file corruption or security violations. Use `ast_validator.py`, `validation_policy.py`, and Landlock descriptors.
- **No Silent Fallbacks**: If a required compiler, binary, or test suite is missing, fail closed with an explicit error—never return a fake success status.
- **Token Economy for Local Models**: Keep prompts and context injections under strict token budgets (<1,000 tokens for RWKV-7 2.9B) using `compact_scaffold.py`.
