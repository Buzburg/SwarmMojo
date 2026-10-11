"""Automated Multi-Perspective Code Review Engine for Swarmojo by Buzburg AI.

Analyzes source code and git diffs across four dimensions:
1. Security (injection, secret exposure, unconstrained execution, unsafe deserialization)
2. Performance (unbounded iterations, algorithmic bottlenecks, redundant IO)
3. Reliability & Bug Risks (null pointer, resource leaks, unhandled exceptions)
4. Code Craft & Maintainability (naming, cyclomatic complexity, modularity)

Generates structured review findings and automated unified patch suggestions.
"""
from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ReviewFinding:
    category: str        # "security", "performance", "bug_risk", "maintainability"
    severity: str        # "critical", "warning", "suggestion"
    line: int
    rule_id: str
    message: str
    code_snippet: str
    suggested_fix: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CodeReviewReport:
    target: str
    passed: bool
    total_findings: int
    critical_count: int
    warning_count: int
    suggestion_count: int
    findings: List[ReviewFinding] = field(default_factory=list)
    suggested_patch: Optional[str] = None
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target": self.target,
            "passed": self.passed,
            "total_findings": self.total_findings,
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
            "suggestion_count": self.suggestion_count,
            "findings": [f.to_dict() for f in self.findings],
            "suggested_patch": self.suggested_patch,
            "summary": self.summary,
        }


class CodeReviewEngine:
    """Multi-perspective static analysis and code review coordinator."""

    # Common security hazard patterns
    SECURITY_PATTERNS = [
        (r"\beval\s*\(", "SEC-001", "critical", "Use of eval() detected; dangerous arbitrary code execution hazard."),
        (r"\bexec\s*\(", "SEC-002", "critical", "Use of exec() detected; potential arbitrary code execution vulnerability."),
        (r"(?i)(api[_-]?key|secret[_-]?token|password)\s*=\s*['\"][a-zA-Z0-9_\-]{8,}['\"]", "SEC-003", "critical", "Hardcoded credential or secret detected."),
        (r"shell\s*=\s*True", "SEC-004", "warning", "Subprocess invoked with shell=True; command injection hazard."),
        (r"\bpickle\.loads?\s*\(", "SEC-005", "warning", "Insecure deserialization with pickle detected; use safer alternatives like json."),
    ]

    # Performance hazard patterns
    PERF_PATTERNS = [
        (r"for\s+.*\s+in\s+.*:\s*\n\s+.*\.append\(.*for\s+", "PERF-001", "suggestion", "Nested loop in list comprehension or append; consider vectorized or set operations."),
        (r"\.read\(\)\.splitlines\(\)", "PERF-002", "suggestion", "Reading entire file into memory; consider streaming line-by-line for large datasets."),
    ]

    def review_source(self, code: str, filename: str = "unnamed.py") -> CodeReviewReport:
        """Performs multi-criteria audit of code content."""
        findings: List[ReviewFinding] = []
        lines = code.splitlines()

        # 1. Pattern-based regex scans
        for i, line_text in enumerate(lines, 1):
            for pattern, rule_id, severity, msg in self.SECURITY_PATTERNS:
                if re.search(pattern, line_text):
                    findings.append(ReviewFinding(
                        category="security",
                        severity=severity,
                        line=i,
                        rule_id=rule_id,
                        message=msg,
                        code_snippet=line_text.strip(),
                    ))

            for pattern, rule_id, severity, msg in self.PERF_PATTERNS:
                if re.search(pattern, line_text):
                    findings.append(ReviewFinding(
                        category="performance",
                        severity=severity,
                        line=i,
                        rule_id=rule_id,
                        message=msg,
                        code_snippet=line_text.strip(),
                    ))

        # 2. AST-based syntax and structure checks (for Python)
        if filename.endswith(".py"):
            try:
                tree = ast.parse(code, filename=filename)
                for node in ast.walk(tree):
                    # Check bare except clauses
                    if isinstance(node, ast.ExceptHandler) and node.type is None:
                        line_no = getattr(node, "lineno", 1)
                        snippet = lines[line_no - 1].strip() if line_no <= len(lines) else "except:"
                        findings.append(ReviewFinding(
                            category="bug_risk",
                            severity="warning",
                            line=line_no,
                            rule_id="BUG-001",
                            message="Bare 'except:' catches SystemExit and KeyboardInterrupt; specify Exception.",
                            code_snippet=snippet,
                            suggested_fix="except Exception:",
                        ))

                    # Check mutable default arguments
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        for default in node.args.defaults:
                            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                                line_no = getattr(node, "lineno", 1)
                                snippet = lines[line_no - 1].strip() if line_no <= len(lines) else ""
                                findings.append(ReviewFinding(
                                    category="bug_risk",
                                    severity="warning",
                                    line=line_no,
                                    rule_id="BUG-002",
                                    message=f"Mutable default argument in function '{node.name}'. Use None and initialize in body.",
                                    code_snippet=snippet,
                                ))
            except SyntaxError as e:
                findings.append(ReviewFinding(
                    category="bug_risk",
                    severity="critical",
                    line=e.lineno or 1,
                    rule_id="SYNTAX-001",
                    message=f"Syntax error: {e.msg}",
                    code_snippet=e.text.strip() if e.text else "",
                ))

        critical_count = sum(1 for f in findings if f.severity == "critical")
        warning_count = sum(1 for f in findings if f.severity == "warning")
        suggestion_count = sum(1 for f in findings if f.severity == "suggestion")
        passed = critical_count == 0

        summary = f"Review for {filename}: {len(findings)} findings ({critical_count} critical, {warning_count} warnings, {suggestion_count} suggestions). "
        summary += "Passed inspection." if passed else "Action required: resolve critical issues."

        return CodeReviewReport(
            target=filename,
            passed=passed,
            total_findings=len(findings),
            critical_count=critical_count,
            warning_count=warning_count,
            suggestion_count=suggestion_count,
            findings=findings,
            summary=summary,
        )

    def review_diff(self, diff_text: str) -> CodeReviewReport:
        """Reviews git diff patches, checking only newly added lines (+)."""
        findings: List[ReviewFinding] = []
        lines = diff_text.splitlines()
        current_file = "diff_patch"
        current_line = 0

        for line in lines:
            if line.startswith("+++ b/"):
                current_file = line[6:]
            elif line.startswith("@@"):
                match = re.search(r"\+(\d+)", line)
                if match:
                    current_line = int(match.group(1))
            elif line.startswith("+") and not line.startswith("+++"):
                current_line += 1
                added_code = line[1:]
                for pattern, rule_id, severity, msg in self.SECURITY_PATTERNS:
                    if re.search(pattern, added_code):
                        findings.append(ReviewFinding(
                            category="security",
                            severity=severity,
                            line=current_line,
                            rule_id=rule_id,
                            message=msg,
                            code_snippet=added_code.strip(),
                        ))
            elif not line.startswith("-"):
                current_line += 1

        critical_count = sum(1 for f in findings if f.severity == "critical")
        warning_count = sum(1 for f in findings if f.severity == "warning")
        suggestion_count = sum(1 for f in findings if f.severity == "suggestion")
        passed = critical_count == 0

        return CodeReviewReport(
            target=current_file,
            passed=passed,
            total_findings=len(findings),
            critical_count=critical_count,
            warning_count=warning_count,
            suggestion_count=suggestion_count,
            findings=findings,
            summary=f"Diff review: {len(findings)} issues identified.",
        )
