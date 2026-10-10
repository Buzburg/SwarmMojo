"""Unit tests verifying the repository enhancements integrated into ROMS:
1. Autonomous Continuous Memory Reflection (reflection.py)
2. Agent Memory LLM Wiki Export (reflection.py)
3. Compact Small-Model Scaffold (compact_scaffold.py)
4. Deterministic AST Safety Gate (ast_validator.py)
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.reflection import ContinuousMemoryReflector, LLMWikiExporter, TaskOutcome
from app.compact_scaffold import (
    CORE_PRIMITIVE_TOOLS,
    build_compact_system_prompt,
    parse_tool_invocation,
)
from app.ast_validator import audit_python_code, audit_file
from app.prompt_builder import estimate_tokens


class RepoEnhancementsTest(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_lessons.db"
        self.wiki_dir = Path(self.temp_dir.name) / "wiki"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_continuous_reflection_success_and_failure(self):
        reflector = ContinuousMemoryReflector(db_path=self.db_path)

        # 1. Reflect on a successful task
        win_outcome = TaskOutcome(
            project_id="omarchy-core",
            target_file="app_mojo/omarchy_broker.mojo",
            action_taken="Added strict JSON key parser",
            succeeded=True,
            task_id="task001",
            revision="abc1234",
            patch_summary="Clean JSON validation"
        )
        res_win = reflector.reflect(win_outcome)
        self.assertEqual(res_win["status"], "reflected_success")
        self.assertEqual(res_win["memory"]["status"], "verified")
        self.assertEqual(res_win["memory"]["outcome"], "success")
        self.assertTrue(res_win["memory"]["recommendation_eligible"])

        # 2. Reflect on a failed task (anti-pattern recording)
        fail_outcome = TaskOutcome(
            project_id="omarchy-core",
            target_file="app_mojo/staging_sandbox.mojo",
            action_taken="Declared syscall with conflicting c_int signature",
            succeeded=False,
            task_id="task002",
            revision="def5678",
            error_log="LLVM lowering error: existing function with conflicting signature"
        )
        res_fail = reflector.reflect(fail_outcome)
        self.assertEqual(res_fail["status"], "reflected_failure")
        self.assertEqual(res_fail["memory"]["status"], "verified")
        self.assertEqual(res_fail["memory"]["outcome"], "failure")
        self.assertFalse(res_fail["memory"]["recommendation_eligible"])
        self.assertIn("AVOID ANTI-PATTERN", str(res_fail["memory"]["summary"]))

    def test_llm_wiki_export(self):
        reflector = ContinuousMemoryReflector(db_path=self.db_path)
        exporter = LLMWikiExporter(db_path=self.db_path)

        reflector.reflect(TaskOutcome(
            project_id="omarchy-core",
            target_file="app/gateway.py",
            action_taken="Bound HTTP listener to 127.0.0.1 loopback",
            succeeded=True,
            task_id="t1"
        ))
        reflector.reflect(TaskOutcome(
            project_id="omarchy-core",
            target_file="app/tools.py",
            action_taken="Nested semaphore acquisition",
            succeeded=False,
            task_id="t2",
            error_log="Deadlock on concurrent MCP tool calls"
        ))

        export_info = exporter.export_project_wiki("omarchy-core", self.wiki_dir)
        self.assertEqual(export_info["success_count"], "1")
        self.assertEqual(export_info["failure_count"], "1")

        lessons_text = Path(export_info["lessons_path"]).read_text(encoding="utf-8")
        anti_text = Path(export_info["anti_patterns_path"]).read_text(encoding="utf-8")

        self.assertIn("127.0.0.1 loopback", lessons_text)
        self.assertIn("Deadlock on concurrent MCP tool calls", anti_text)

    def test_compact_scaffold_budget_and_tools(self):
        # Verify 4 core primitive tools
        self.assertEqual(len(CORE_PRIMITIVE_TOOLS), 4)
        tool_names = [t["name"] for t in CORE_PRIMITIVE_TOOLS]
        self.assertEqual(
            tool_names,
            ["read_file", "write_file", "edit_file", "run_sandbox_command"]
        )

        # Verify prompt is well under 1,000 tokens
        prompt = build_compact_system_prompt(
            persona_name="Goose",
            project_id="omarchy-core",
            custom_instructions="Keep diffs minimal and preserve comments."
        )
        token_count = estimate_tokens(prompt)
        self.assertLess(token_count, 500, f"Prompt too large: {token_count} tokens")
        self.assertIn("[SYSTEM_ANCHOR]", prompt)
        self.assertIn("Epoch Year: 2026", prompt)

        # Verify strict JSON tool invocation parsing
        raw_output = 'Here is the action:\n```json\n{"tool": "read_file", "arguments": {"path": "app/memory.py", "offset": 1, "limit": 40}}\n```'
        parsed = parse_tool_invocation(raw_output)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["tool"], "read_file")
        self.assertEqual(parsed["arguments"]["path"], "app/memory.py")

    def test_deterministic_ast_gate(self):
        # 1. Valid safe Python code passes
        safe_code = "def add(a: int, b: int) -> int:\n    return a + b\n"
        res_safe = audit_python_code(safe_code, "math_utils.py")
        self.assertTrue(res_safe["passed"])
        self.assertTrue(res_safe["syntax_valid"])
        self.assertEqual(len(res_safe["violations"]), 0)

        # 2. Syntax error is caught deterministically
        broken_code = "def broken(\n    return 42"
        res_broken = audit_python_code(broken_code, "broken.py")
        self.assertFalse(res_broken["passed"])
        self.assertFalse(res_broken["syntax_valid"])
        self.assertEqual(res_broken["violations"][0]["rule"], "SYNTAX-ERROR")

        # 3. Dangerous eval / os.system / sensitive path are blocked
        unsafe_code = (
            "import os, subprocess\n"
            "def exploit(user_input):\n"
            "    eval(user_input)\n"
            "    os.system('rm -rf /')\n"
            "    subprocess.Popen('ls', shell=True)\n"
            "    secret = open('/etc/shadow').read()\n"
        )
        res_unsafe = audit_python_code(unsafe_code, "exploit.py")
        self.assertFalse(res_unsafe["passed"])
        rules = {v["rule"] for v in res_unsafe["violations"]}
        self.assertIn("SEC-BUILTIN-EVAL", rules)
        self.assertIn("SEC-MOD-os-system", rules)
        self.assertIn("SEC-SUBPROCESS-SHELL", rules)
        self.assertIn("SEC-SENSITIVE-PATH", rules)


if __name__ == "__main__":
    unittest.main()
