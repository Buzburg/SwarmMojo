"""Bounded local evidence search, claim checks, and staged code review."""

import ast
import os
from pathlib import Path
import re

from .memory import digest

TEXT = {'.py', '.js', '.ts', '.tsx', '.jsx', '.rs', '.go', '.c', '.h', '.cpp',
        '.md', '.txt', '.toml', '.json', '.yaml', '.yml', '.sh', '.qml', '.css', '.html'}


def documents(tools, path='.', max_files=200):
    """Cap directory traversal too; empty directories cannot create unbounded work."""
    root = tools.path(path)
    if not root.exists():
        raise ValueError('Search path does not exist')
    pending, docs, errors = [root], [], []
    inspected = 0
    partial = False
    while pending and inspected < 2000 and len(docs) < max_files:
        item = pending.pop()
        inspected += 1
        rel = str(item.relative_to(tools.root))
        try:
            tools.path(rel)
            if item.is_dir():
                if item.name in {'node_modules', '__pycache__', '.venv', 'target', 'dist', 'build'}:
                    continue
                children = []
                with os.scandir(item) as entries:
                    for entry in entries:
                        if len(children) + len(pending) >= 2000 - inspected:
                            partial = True
                            break
                        children.append(Path(entry.path))
                pending.extend(sorted(children, reverse=True))
            elif item.suffix.lower() in TEXT or item.name in {'Makefile', 'Dockerfile'}:
                doc = tools.read(rel, limit=32000)
                if '\x00' in doc['text']:
                    continue
                partial |= doc['truncated']
                docs.append(doc)
        except (OSError, ValueError) as exc:
            # Private paths are deliberately outside search scope, not missing evidence.
            if 'excluded' not in str(exc):
                errors.append({'path': rel, 'error': str(exc)})
    return docs, {'partial': partial or bool(pending) or bool(errors), 'errors': errors[:10],
                  'files_read': len(docs), 'scope': 'Allowed text files; at most 2000 entries and 32000 bytes per file'}


def search(tools, query, path='.', judge=None):
    terms = set(re.findall(r'\w+', query.casefold()))
    if not terms or len(query) > 4000:
        raise ValueError('Search needs a bounded nonempty query')
    docs, coverage = documents(tools, path)
    candidates, seen = [], set()
    for doc in docs:
        lines = doc['text'].splitlines()
        for index, line in enumerate(lines):
            words = set(re.findall(r'\w+', line.casefold()))
            score = len(terms & words)
            if not score:
                continue
            start, end = max(0, index-1), min(len(lines), index+2)
            snippet = '\n'.join(lines[start:end])[:1200]
            key = digest(snippet)
            if key in seen:
                continue
            seen.add(key)
            candidates.append({'path': doc['path'], 'sha256': doc['sha256'],
                               'line': start+1, 'end_line': end, 'text': snippet,
                               'lexical_score': score})
    candidates.sort(key=lambda c: (-c['lexical_score'], c['path'], c['line']))
    result = {'ok': True, 'matches': candidates[:12], 'coverage': coverage, 'ranking': 'lexical'}
    if judge and candidates:
        shortlist = candidates[:6]
        try:
            answer = judge.ask({'query': query, 'candidates': shortlist}, [{
                'id': 'best', 'type': 'choice', 'question': 'Which candidate best answers the query?',
                'options': {**{str(i): f'Candidate {i}' for i in range(len(shortlist))},
                            'none': 'None provides relevant evidence'}}])['best']
            result['judgment'] = answer
            if answer['choice'] != 'none' and answer['margin'] >= .3:
                chosen = shortlist[int(answer['choice'])]
                result['matches'].remove(chosen)
                result['matches'].insert(0, chosen)
                result['ranking'] = 'semantic_advisory'
        except (RuntimeError, ValueError, KeyError) as exc:
            result['judgment_error'] = str(exc)
    return result


def verify_claim(tools, path, claim, quote, judge=None):
    if not claim or not quote or len(claim) > 4000 or len(quote) > 4000:
        raise ValueError('Claim and exact quote must contain 1..4000 characters')
    doc = tools.read(path, limit=32000)
    offset = doc['text'].find(quote)
    result = {'ok': True, 'path': path, 'sha256': doc['sha256'],
              'quote_found': offset >= 0, 'status': 'unsupported', 'provisional': True}
    if offset < 0:
        result['reason'] = 'Exact quote was not found in the bounded file evidence'
        return result
    result.update(line=doc['text'][:offset].count('\n')+1, quote=quote)
    result['status'] = 'quote_verified_claim_unchecked'
    if judge:
        answer = judge.ask({'claim': claim, 'quote': quote}, [{
            'id': 'claim', 'type': 'choice', 'question': 'Does this exact evidence establish the claim?',
            'options': {'supported': 'Directly supported by the evidence',
                        'contradicted': 'Directly contradicted by the evidence',
                        'unsupported': 'Missing, ambiguous, or insufficient evidence'}}])['claim']
        result['judgment'] = answer
        result['status'] = answer['choice'] if answer['margin'] >= .3 else 'unsupported'
    return result


def review(tools, path='.', judge=None):
    docs, coverage = documents(tools, path, max_files=12)
    findings, screened, followups = [], 0, 0
    for doc in docs:
        if doc['path'].endswith('.py') and not doc['truncated']:
            try:
                ast.parse(doc['text'], filename=doc['path'])
            except SyntaxError as exc:
                findings.append({'path': doc['path'], 'sha256': doc['sha256'], 'line': exc.lineno,
                                 'kind': 'syntax_error', 'message': exc.msg, 'verified': True})
        if not judge or followups >= 4:
            continue
        lines = doc['text'].splitlines()
        # Locations are created from observed source, never generated by a model.
        regions = [{'line': i+1, 'end_line': min(i+20, len(lines)),
                    'text': '\n'.join(lines[i:i+20])[:1600]} for i in range(0, min(len(lines), 240), 20)]
        if not regions:
            continue
        try:
            screen = judge.ask({'path': doc['path'], 'regions': regions}, [{
                'id': 'risk', 'type': 'choice', 'question': 'Is a concrete correctness defect visible?',
                'options': {'issue': 'Concrete defect supported by visible code',
                            'clear': 'No visible defect', 'uncertain': 'More context required'}}])['risk']
            screened += 1
            if screen['choice'] != 'issue' or screen['margin'] < .3:
                continue
            followups += 1
            location = judge.ask({'path': doc['path'], 'regions': regions}, [{
                'id': 'evidence', 'type': 'choice', 'question': 'Select the strongest defect evidence.',
                'options': {**{str(i): f'Region {i}' for i in range(len(regions))},
                            'none': 'No region supports a concrete defect'}}])['evidence']
            if location['choice'] == 'none' or location['margin'] < .3:
                continue
            region = regions[int(location['choice'])]
            mechanism = judge.ask(region, [{
                'id': 'mechanism', 'type': 'choice', 'question': 'What failure is evidenced by this code?',
                'options': {'validation': 'Invalid input can cause incorrect behavior',
                            'state': 'State updates or lifecycle ordering are incorrect',
                            'failure': 'Error handling loses or misreports failure',
                            'resource': 'Resource use or cleanup is incorrect',
                            'none': 'No specific failure mechanism is established'}},
                {'id': 'severity', 'type': 'score', 'question': 'Assess demonstrated impact, not hypothetical impact.',
                 'options': ['Unclear or negligible', 'Limited incorrect behavior', 'Major functionality failure']}])
            if mechanism['mechanism']['choice'] != 'none':
                findings.append({'path': doc['path'], 'sha256': doc['sha256'], **region,
                                 'kind': mechanism['mechanism']['choice'], 'verified': False,
                                 'message': 'Potential defect; inspect cited evidence', 'judgments': mechanism})
        except (RuntimeError, ValueError, KeyError) as exc:
            coverage['semantic_error'] = str(exc)
            break
    return {'ok': True, 'findings': findings, 'coverage': coverage, 'files_screened': screened,
            'scope': 'Python syntax plus optional bounded semantic review; absence of findings is not proof of correctness'}
