"""Deterministic diagnostics first; semantic classification is advisory."""

import os
import re

ADVICE = {
    "transient": "A temporary failure may recover. Retry only a known read-only tool, once.",
    "environment": "Check dependencies, repository location, or an occupied port.",
    "code_bug": "Inspect the diagnostic and fix the code before another attempt.",
    "permission": "Resolve the missing permission; do not retry unchanged or bypass it.",
    "user_error": "Correct the command arguments or requested path.",
    "unknown": "Inspect the available evidence; do not guess that a retry is safe.",
    "no_failure": "No failure reported.",
}


def repeated_failure(events):
    """Stop three consecutive same-tool, identical-diagnostic failures.

    Arguments may differ. Success or a different diagnostic breaks the streak;
    timings and semantic classifications never determine this stop.
    """
    recent = [e for e in events if e.get('kind') == 'tool'][-3:]
    if len(recent) != 3 or any(e['result'].get('ok') for e in recent):
        return None
    signatures = [(e['action']['tool'], str(e['result'].get('error', '')).strip(),
                   str(e['result'].get('output', '')).strip()) for e in recent]
    if signatures[0] == signatures[1] == signatures[2] and any(signatures[0][1:]):
        return {'policy': 'three consecutive identical failures from the same tool',
                'observed_event_ids': [e['event_id'] for e in recent],
                'tool': signatures[0][0]}
    return None


def redact(value, preserve_positions=False):
    """Best-effort credential redaction before outputs enter model context/audit."""
    if isinstance(value, dict):
        return {k: redact(v, preserve_positions) for k,v in value.items()}
    if isinstance(value, list):
        return [redact(v, preserve_positions) for v in value]
    if not isinstance(value, str):
        return value
    def replacement(text, label='[REDACTED]'):
        return ''.join(c if c in '\r\n' else '*' for c in text) if preserve_positions else label
    for name, secret in os.environ.items():
        if len(secret) >= 8 and any(name.upper().endswith(s) for s in ("API_KEY", "TOKEN", "PASSWORD", "SECRET")):
            value = value.replace(secret, replacement(secret))
    value = re.sub(r"-----BEGIN (?:[A-Z ]*PRIVATE KEY)-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)",
                   lambda m: replacement(m[0], '[REDACTED PRIVATE KEY]'), value)
    value = re.sub(r"(?i)(\b(?:api[_-]?key|access[_-]?token|password|secret)\s*[=:]\s*)([^\s,;]+)",
                   lambda m: m[1]+replacement(m[2]), value)
    return re.sub(r"(?i)(\bBearer\s+)([A-Za-z0-9._~+/-]{8,}=*)", lambda m: m[1]+replacement(m[2]), value)


def diagnose(result, judge=None):
    if result.get("ok"):
        label = "no_failure"
    else:
        text = str(result.get("error", "")) + "\n" + str(result.get("output", ""))
        rules = [
            ("permission", r"permission denied|access denied|EACCES|EPERM|HTTP (?:401|403)"),
            ("environment", r"command not found|No such file|not a git repository|EADDRINUSE|No module named"),
            ("code_bug", r"SyntaxError|AssertionError|TypeError|error TS\d+|FAILED .*test"),
            ("user_error", r"unrecognized arguments|unknown option|invalid argument|usage:"),
            ("transient", r"ECONNRESET|connection reset|temporarily unavailable|HTTP (?:429|502|503|504)"),
        ]
        label = next((name for name, pattern in rules if re.search(pattern, text, re.I)), "unknown")
    answer = {"class": label, "source": "deterministic", "advice": ADVICE[label], "retry_safe": False}
    if label == "unknown" and judge:
        try:
            scored = judge.ask(redact(result), [{"id": "failure", "type": "choice",
                "question": "Classify the observed failure. Do not infer whether rerunning a command is safe.",
                "options": {k:v for k,v in ADVICE.items() if k != "no_failure"}}])["failure"]
            chosen = scored["choice"]
            answer["judgment"] = scored
            if scored["probabilities"][chosen] >= 0.9 and scored["margin"] >= 0.3:
                answer.update({"class": chosen, "source": "semantic_advisory", "advice": ADVICE[chosen]})
        except (RuntimeError, ValueError) as exc:
            answer["judge_error"] = str(exc)
    return answer
