"""Bounded, user-authored completion criteria. No executable expressions."""

import re

CHECKS = {'file_exists': {'path'}, 'file_absent': {'path'},
          'file_contains': {'path', 'text'}, 'file_sha256': {'path', 'sha256'},
          'command_passed': {'index'}}


def validate(tree):
    seen = set()
    def visit(node, depth):
        if depth > 4 or len(seen) >= 32:
            raise ValueError('Requirements permit at most 32 nodes and depth 4')
        if not isinstance(node, dict) or set(node)-{'id', 'description', 'children', 'check'}:
            raise ValueError('Requirement needs id, description, and children or check')
        if not isinstance(node.get('id'), str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', node['id']) or node['id'] in seen:
            raise ValueError('Requirement IDs must be unique bounded identifiers')
        seen.add(node['id'])
        if not isinstance(node.get('description'), str) or not 1 <= len(node['description']) <= 1000:
            raise ValueError('Requirement description must contain 1..1000 characters')
        if ('check' in node) == ('children' in node):
            raise ValueError('Each requirement must have either check or children')
        if 'children' in node:
            if not isinstance(node['children'], list) or not 1 <= len(node['children']) <= 16:
                raise ValueError('Requirement groups need 1..16 children')
            for child in node['children']:
                visit(child, depth+1)
        else:
            check = node['check']
            if not isinstance(check, dict) or not isinstance(check.get('type'), str) or check['type'] not in CHECKS:
                raise ValueError('Unknown requirement check')
            if set(check) != CHECKS[check['type']] | {'type'}:
                raise ValueError('Requirement check fields do not match its type')
            for key,value in check.items():
                if key in {'path', 'text'} and (not isinstance(value, str) or not 1 <= len(value) <= 4000 or '\x00' in value):
                    raise ValueError(f'Invalid requirement {key}')
            if check['type'] == 'file_sha256' and (not isinstance(check['sha256'], str) or not re.fullmatch(r'[a-f0-9]{64}', check['sha256'])):
                raise ValueError('Requirement sha256 must be 64 lowercase hex digits')
            if check['type'] == 'command_passed' and (type(check['index']) is not int or not 0 <= check['index'] <= 2):
                raise ValueError('Command check index must be 0..2')
    visit(tree, 0)
    return tree


def evaluate(tree, tools, verification=None):
    validate(tree)
    counts = {'passed': 0, 'failed': 0, 'unknown': 0}
    def visit(node):
        result = {'id': node['id'], 'description': node['description']}
        if 'children' in node:
            children = [visit(child) for child in node['children']]
            statuses = {child['status'] for child in children}
            result.update(children=children, status='failed' if 'failed' in statuses else 'unknown' if 'unknown' in statuses else 'passed')
            return result
        check = node['check']
        kind = check['type']
        try:
            observation = {'check_type': kind}
            if kind == 'command_passed':
                checks = verification.get('checks', []) if verification else []
                if check['index'] >= len(checks):
                    raise ValueError('No result for this explicitly authorized verification command')
                command = checks[check['index']]
                passed = command['result'].get('ok') is True
                observation.update(index=check['index'], result=command['result'])
            else:
                target = tools.path(check['path'])
                observation['path'] = check['path']
                if kind in {'file_exists', 'file_absent'}:
                    passed = target.is_file() if kind == 'file_exists' else not target.exists()
                    observation['exists'] = target.exists()
                    observation['is_file'] = target.is_file()
                else:
                    document = tools.read(check['path'], limit=2_000_000)
                    observation['sha256'] = document['sha256']
                    passed = check['text'] in document['text'] if kind == 'file_contains' else check['sha256'] == document['sha256']
            result.update(status='passed' if passed else 'failed', observation=observation)
        except (OSError, ValueError) as exc:
            result.update(status='unknown', observation={'check_type': kind, 'error': str(exc)})
        counts[result['status']] += 1
        return result
    result = visit(tree)
    return {'ok': result['status'] == 'passed', 'tree': result, 'leaves': counts,
            'progress': counts['passed']/sum(counts.values()),
            'scope': 'All declared leaves must pass; progress is not a probability or proof of undeclared requirements'}
