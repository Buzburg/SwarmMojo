"""Reviewed executable workflows with observed conditions, not inferred effects."""

import json
import re
import time

from .memory import digest, packed
from .requirements import validate as validate_requirements, evaluate
from .tools import validate_action


def file_conditions(tree):
    validate_requirements(tree)
    if 'children' in tree:
        for child in tree['children']:
            file_conditions(child)
    elif tree['check']['type'] == 'command_passed':
        raise ValueError('Workflow conditions use file evidence; use --verify-command for a separate command gate')


def validate(plan):
    if not isinstance(plan, dict) or set(plan) != {'name', 'description', 'steps', 'completion'}:
        raise ValueError('Workflow needs name, description, steps, completion')
    if not isinstance(plan['name'], str) or not re.fullmatch(r'[a-z0-9_-]{1,64}', plan['name']):
        raise ValueError('Invalid workflow name')
    if not isinstance(plan['description'], str) or not 1 <= len(plan['description']) <= 1000:
        raise ValueError('Invalid workflow description')
    if not isinstance(plan['steps'], list) or not 1 <= len(plan['steps']) <= 16:
        raise ValueError('Workflow needs 1..16 steps')
    for step in plan['steps']:
        if not isinstance(step, dict) or set(step) != {'action', 'before', 'after'}:
            raise ValueError('Step needs action, before, after')
        validate_action(step['action'])
        for key in ('before', 'after'):
            file_conditions(step[key])
    file_conditions(plan['completion'])
    if len(packed(plan).encode()) > 64000:
        raise ValueError('Workflow exceeds 64 KB')
    return plan


class Workflows:
    def __init__(self, memory, workspace):
        from pathlib import Path
        self.memory, self.db = memory, memory.db
        self.workspace = str(Path(workspace).resolve())
        self.db.execute('''CREATE TABLE IF NOT EXISTS workflows (
            id TEXT PRIMARY KEY, workspace TEXT, name TEXT, plan TEXT,
            source_session TEXT, reviewed INTEGER DEFAULT 0, regression TEXT, created REAL)''')
        self.db.commit()

    def propose(self, plan, source_session=None):
        validate(plan)
        if source_session is not None:
            session = self.memory.session(source_session)
            if session['workspace'] != self.workspace or session['status'] != 'complete':
                raise ValueError('Workflow learning requires a completed session in this workspace')
            events = self.memory.events(source_session)
            actions = [e['action'] for e in events if e['kind'] == 'tool' and e['result'].get('ok')]
            if actions != [step['action'] for step in plan['steps']]:
                raise ValueError('Proposed actions must match successful source-session actions')
        key = digest([self.workspace, plan, source_session])
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO workflows(id,workspace,name,plan,source_session,created) VALUES(?,?,?,?,?,?)',
                            (key, self.workspace, plan['name'], packed(plan), source_session, time.time()))
        return self.get(key)

    def get(self, key):
        row = self.db.execute('SELECT * FROM workflows WHERE id=? AND workspace=?', (key, self.workspace)).fetchone()
        if row is None:
            raise ValueError('Unknown workflow in this workspace')
        result = dict(row)
        result['plan'] = json.loads(result['plan'])
        result['regression'] = json.loads(result['regression']) if result['regression'] else None
        return result

    def list(self):
        return [self.get(row[0]) for row in self.db.execute(
            'SELECT id FROM workflows WHERE workspace=? ORDER BY created DESC LIMIT 100', (self.workspace,))]

    def named(self, name):
        matches = self.db.execute('SELECT id FROM workflows WHERE workspace=? AND name=? AND reviewed=1 LIMIT 2',
                                  (self.workspace, name)).fetchall()
        if not matches:
            raise ValueError('No reviewed workflow with this exact name in this workspace')
        if len(matches) != 1:
            raise ValueError('Multiple reviewed workflows have this name; select the exact workflow ID')
        return self.approved(matches[0][0])

    def review(self, key):
        record = self.get(key)
        if not record['regression'] or not record['regression'].get('ok'):
            raise ValueError('A passing fixture regression is required before review approval')
        with self.db:
            self.db.execute('UPDATE workflows SET reviewed=1 WHERE id=?', (key,))
        return self.get(key)

    def learn(self, source_session, name):
        """Draft exact file workflows from successful observations, never approve."""
        session = self.memory.session(source_session)
        if session['workspace'] != self.workspace or session['status'] != 'complete':
            raise ValueError('Learn only from a completed task in this workspace')
        events = [e for e in self.memory.events(source_session) if e['kind'] == 'tool']
        if not events or any(not e['result'].get('ok') or e['action']['tool'] not in {'read_file', 'write_file', 'edit_file'} for e in events):
            raise ValueError('Automatic learning supports successful full-read/write/edit-file tasks; author other plans explicitly')
        def condition(path, sha):
            check = {'type': 'file_absent', 'path': path} if sha == 'missing' else {'type': 'file_sha256', 'path': path, 'sha256': sha}
            return {'id': 'file', 'description': 'Observed state of '+path, 'check': check}
        steps, initial, touched, final = [], {}, set(), {}
        import hashlib
        for event in events:
            action, result = event['action'], event['result']
            path = action['args']['path']; after = result['sha256']
            before = action['args']['expected_sha256'] if action['tool'] in {'write_file', 'edit_file'} else after
            if path not in touched and before != 'missing':
                text = result.get('text') if action['tool'] == 'read_file' else None
                if text is None or hashlib.sha256(text.encode()).hexdigest() != before:
                    raise ValueError('A complete initial file read is needed to create replay fixtures')
                initial[path] = text
            touched.add(path)
            steps.append({'action': action, 'before': condition(path, before), 'after': condition(path, after)})
            final[path] = after
        completion = {'id': 'complete', 'description': 'Verify all final file states', 'children': []}
        for index, (path, sha) in enumerate(final.items()):
            node = condition(path, sha); node['id'] = 'file'+str(index); completion['children'].append(node)
        plan = {'name': name, 'description': 'Exact observed workflow from task '+source_session,
                'steps': steps, 'completion': completion}
        record = self.propose(plan, source_session)
        return {'workflow': record, 'fixtures': [{'files': initial, 'expect': 'complete'}],
                'note': 'Review recorded contents and checks. This reproduces exact files, not a parameterized general skill.'}

    def approved(self, key):
        record = self.get(key)
        if not record['reviewed']:
            raise ValueError('Review the workflow before reuse')
        return record['plan']

    def regress(self, key, fixtures, config):
        plan = self.get(key)['plan']
        report = self._evaluate(plan, fixtures, config)
        with self.db:
            self.db.execute('UPDATE workflows SET regression=?,reviewed=0 WHERE id=?', (packed(report), key))
        return report

    def compare(self, candidate, baseline, fixtures, config):
        """Compare on identical external checks; never promote or revoke a plan."""
        candidate_plan, baseline_plan = self.get(candidate)['plan'], self.get(baseline)['plan']
        if not isinstance(fixtures, list) or not fixtures or any(
                not isinstance(f, dict) or 'checks' not in f for f in fixtures):
            raise ValueError('Comparison requires independent checks on every fixture')
        old = self._evaluate(baseline_plan, fixtures, config)
        new = self._evaluate(candidate_plan, fixtures, config)
        gains = [i for i, (a, b) in enumerate(zip(old['results'], new['results'])) if not a['ok'] and b['ok']]
        regressions = [i for i, (a, b) in enumerate(zip(old['results'], new['results'])) if a['ok'] and not b['ok']]
        step_delta = sum(r['tool_steps'] for r in new['results']) - sum(r['tool_steps'] for r in old['results'])
        improved = new['ok'] and not regressions and (bool(gains) or (old['ok'] and step_delta < 0))
        return {'ok': new['ok'] and not regressions, 'candidate': candidate, 'baseline': baseline,
                'candidate_report': new, 'baseline_report': old,
                'gained_fixtures': gains, 'regressed_fixtures': regressions,
                'tool_step_delta': step_delta, 'measured_improvement': improved,
                'recommendation': 'review_candidate' if improved else 'no_demonstrated_improvement',
                'config_hash': digest(config),
                'scope': 'Same supplied fixtures only; indices are zero-based. No approval or model weights changed. '
                         'Use separate held-out fixtures to assess generalization; steps are not latency.'}

    def _evaluate(self, plan, fixtures, config):
        """Run read/write-file workflows only in disposable fixture workspaces."""
        from pathlib import Path
        import tempfile
        from .engine import Harness
        from .memory import Memory
        from .tools import Tools
        if any(s['action']['tool'] not in {'read_file', 'read_lines', 'write_file', 'edit_file', 'list_files', 'search'} for s in plan['steps']):
            raise ValueError('Fixture runner supports only local file tools; no commands or desktop/network actions')
        if not isinstance(fixtures, list) or not 1 <= len(fixtures) <= 10 or len(packed(fixtures).encode()) > 128000:
            raise ValueError('Provide 1..10 bounded regression fixtures')
        # Validate the suite schema before starting disposable execution.
        for fixture in fixtures:
            if (not isinstance(fixture, dict) or not {'files', 'expect'} <= set(fixture)
                    or set(fixture)-{'files', 'expect', 'checks'}
                    or fixture['expect'] not in {'complete', 'blocked', 'needs_verification'}):
                raise ValueError('Fixture needs files, expected status and optional independent checks')
            if not isinstance(fixture['files'], dict) or len(fixture['files']) > 32:
                raise ValueError('Fixture files must be a bounded map')
            if 'checks' in fixture:
                file_conditions(fixture['checks'])
        results = []
        for fixture in fixtures:
            with tempfile.TemporaryDirectory(prefix='aeon-regression-') as tmp:
                root = Path(tmp)/'workspace'; root.mkdir()
                tools = Tools(root)
                for path, text in fixture['files'].items():
                    if not isinstance(text, str):
                        raise ValueError('Fixture contents must be text')
                    target = tools.path(path); target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(text.encode())
                memory = Memory(Path(tmp)/'state')
                try:
                    actual = Harness(config, memory, root).run('Workflow regression', offline=True, allow_write=True, workflow=plan)
                    outcome = evaluate(fixture['checks'], tools) if 'checks' in fixture else None
                    results.append({'expected': fixture['expect'], 'actual': actual['status'],
                                    'ok': actual['status'] == fixture['expect'] and (outcome is None or outcome['ok']),
                                    'independent_checks': outcome,
                                    'tool_steps': sum(e['kind'] == 'tool' for e in memory.events(actual['session'])),
                                    'llm_calls': actual['llm_calls'],
                                    'verification': actual['verification']})
                finally:
                    memory.close()
        report = {'ok': all(r['ok'] for r in results) and any(r['actual'] == 'complete' for r in results),
                  'fixtures_hash': digest(fixtures), 'plan_hash': digest(plan), 'results': results,
                  'independently_checked': all('checks' in f for f in fixtures),
                  'scope': 'Disposable fixtures only; does not prove behavior on other workspaces'}
        return report
