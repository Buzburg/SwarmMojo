"""Bounded advisory context using the local Symdex and Sieve prototypes."""
from __future__ import annotations

import ast
import hashlib
import os
import re
from pathlib import Path
from typing import Any

from app.patch_tasks import FORBIDDEN, patch_path, read_file

from .vendor.sieve import score_line
from .vendor.symdex import CALL_PATTERN, DEF_PATTERNS, SUPPORTED_EXTS


def compact_log(text: str, *, max_lines: int = 60, max_bytes: int = 6000) -> dict:
    if (type(max_lines) is not int or not 1 <= max_lines <= 1000
            or type(max_bytes) is not int or not 64 <= max_bytes <= 65536):
        raise ValueError('Invalid diagnostic output budget')
    raw = text.encode('utf-8')
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError('Diagnostic input exceeds 10 MiB; use the original log file')
    lines = text.splitlines()
    important = {i for i, line in enumerate(lines) if score_line(line) >= 0.8}
    neighbors = {n for i in important for n in range(max(0, i - 2), min(len(lines), i + 3))}
    edges = set(range(min(3, len(lines)))) | set(range(max(0, len(lines) - 5), len(lines)))
    ranked = sorted(range(len(lines)), key=lambda i: (0 if i in important else
        1 if i in edges else 2 if i in neighbors else 3, i))
    selected = sorted(ranked[:max_lines])
    output: list[str] = []
    remaining = max_bytes
    for i in selected:
        separator = 1 if output else 0
        if remaining <= separator:
            break
        line = lines[i].encode('utf-8')[:remaining - separator].decode('utf-8', errors='ignore')
        output.append(line)
        remaining -= len(line.encode('utf-8')) + separator
    result = '\n'.join(output)
    return {'text': result, 'original_lines': len(lines), 'returned_lines': len(output),
            'truncated': result != text, 'raw_sha256': hashlib.sha256(raw).hexdigest()}


class CodeIndex:
    """Refresh on each query; indexes are advisory and never choose editable paths."""
    def __init__(self, root: Path, *, max_files: int = 512) -> None:
        self.root = Path(root).absolute()
        if self.root.resolve() != self.root or not self.root.is_dir():
            raise ValueError('Index root must be an existing directory without symlinks')
        if type(max_files) is not int or not 1 <= max_files <= 4096:
            raise ValueError('Invalid file budget')
        self.max_files = max_files

    def query(self, symbol: str) -> dict:
        if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,127}', symbol):
            raise ValueError('Expected a bounded symbol name')
        result: dict[str, Any] = {'symbol': symbol, 'definitions': [], 'callers': [], 'skipped': [],
                  'indexed_files': 0, 'truncated': False, 'advisory_only': True}
        excluded = FORBIDDEN | {'.pixi', '.venv', 'venv', 'node_modules', 'target',
            '.build-venv', '.build-cache', '.mojo_symdex', 'data', 'models', 'vendor', 'build', 'dist'}
        visited = 0
        for directory, folders, files in os.walk(self.root, followlinks=False):
            visited += len(folders)
            if visited > 10000:
                result['truncated'] = True
                return result
            folders[:] = sorted(n for n in folders if n.lower() not in excluded and
                not n.startswith('.') and not (Path(directory) / n).is_symlink())
            for filename in sorted(files):
                visited += 1
                if visited > 10000 or result['indexed_files'] >= self.max_files:
                    result['truncated'] = True
                    return result
                path = Path(directory) / filename
                if path.suffix not in SUPPORTED_EXTS or filename.startswith('.'):
                    continue
                relative = path.relative_to(self.root).as_posix()
                try:
                    patch_path(relative)
                    raw = read_file(self.root, relative)
                    if raw is None or len(raw) > 256 * 1024 or b'\0' in raw:
                        raise ValueError('Missing, binary, or oversized source')
                    source = raw.decode('utf-8')
                    digest = hashlib.sha256(raw).hexdigest()
                    definitions, callers = self._symbols(source, path.suffix, symbol)
                    for field, items in [('definitions', definitions), ('callers', callers)]:
                        for line in items:
                            if len(result[field]) >= 64:
                                result['truncated'] = True
                                break
                            result[field].append({'path': relative, 'line': line,
                                'sha256': digest, 'method': 'ast' if path.suffix == '.py' else 'heuristic'})
                    result['indexed_files'] += 1
                except (OSError, ValueError, SyntaxError) as error:
                    if len(result['skipped']) < 64:
                        result['skipped'].append({'path': relative, 'reason': type(error).__name__})
        return result

    @staticmethod
    def _symbols(source: str, suffix: str, symbol: str) -> tuple[list[int], list[int]]:
        if suffix == '.py':
            tree = ast.parse(source)
            definitions, callers = [], []
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == symbol:
                    definitions.append(node.lineno)
                elif isinstance(node, ast.Call):
                    name = node.func.id if isinstance(node.func, ast.Name) else (
                        node.func.attr if isinstance(node.func, ast.Attribute) else '')
                    if name == symbol:
                        callers.append(node.lineno)
            return sorted(definitions), sorted(callers)
        definitions, callers = [], []
        for number, line in enumerate(source.splitlines(), 1):
            matches = [pattern.match(line) for pattern in DEF_PATTERNS]
            if any(match and match.group(1) == symbol for match in matches):
                definitions.append(number)
            elif any(match.group(1) == symbol for match in CALL_PATTERN.finditer(line)):
                callers.append(number)
        return definitions, callers
