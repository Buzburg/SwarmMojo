"""Persistent, locally validated inputs that produce ordinary workflow drafts."""

import json
import re
import uuid
from pathlib import Path

from .memory import Memory, packed
from .tools import Tools
from .workflows import Workflows, validate


def checked_value(spec: dict, value: object, tools: Tools) -> str | int:
    kind = spec['type']
    if kind == 'integer':
        if type(value) is not int or not spec['min'] <= value <= spec['max']:
            raise ValueError('Expected an integer within the declared range')
    else:
        if not isinstance(value, str) or not 1 <= len(value.encode()) <= 4000 or '\x00' in value:
            raise ValueError('Expected nonempty text of at most 4000 UTF-8 bytes')
        if kind == 'choice' and value not in spec['choices']:
            raise ValueError('Choose one of the declared values')
        if kind == 'path':
            tools.path(value)
    return value


def bind(template: dict, values: dict, tools: Tools) -> dict:
    """Replace whole argument/check values only; never interpret inserted text."""
    if not isinstance(values, dict) or set(values) != set(template['inputs']):
        raise ValueError('Provide exactly the declared inputs')
    checked = {key: checked_value(spec, values[key], tools) for key, spec in template['inputs'].items()}

    def visit(node: object, path: tuple = ()) -> object:
        if isinstance(node, dict):
            if 'input' in node:
                if (set(node) != {'input'} or not isinstance(node['input'], str)
                        or node['input'] not in checked or len(path) < 2
                        or path[-2] not in {'args', 'check'}
                        or path[-1] in {'type', 'expected_sha256', 'sha256', 'index', 'argv'}):
                    raise ValueError('Input references belong only in tool arguments or file path/text checks')
                return checked[node['input']]
            return {key: visit(value, path + (key,)) for key, value in node.items()}
        if isinstance(node, list):
            return [visit(value, path + (index,)) for index, value in enumerate(node)]
        return node

    plan = visit(template['workflow'])
    validate(plan)
    for step in plan['steps']:
        if 'path' in step['action']['args']:
            tools.path(step['action']['args']['path'])
    return plan


def validate_template(template: dict, tools: Tools) -> None:
    if (not isinstance(template, dict) or set(template) != {'inputs', 'workflow'}
            or len(packed(template).encode()) > 64000
            or not isinstance(template['inputs'], dict) or not 1 <= len(template['inputs']) <= 8):
        raise ValueError('Template needs 1..8 inputs and a workflow, within 64 KB')
    samples = {}
    for name, spec in template['inputs'].items():
        if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', name) or not isinstance(spec, dict):
            raise ValueError('Invalid input name or specification')
        kind = spec.get('type')
        extra = {'min', 'max'} if kind == 'integer' else {'choices'} if kind == 'choice' else set()
        if (kind not in {'text', 'path', 'integer', 'choice'} or set(spec) != {'type', 'prompt'} | extra
                or not isinstance(spec['prompt'], str) or not 1 <= len(spec['prompt']) <= 300):
            raise ValueError('Invalid input type, prompt, or fields')
        if kind == 'integer':
            if type(spec['min']) is not int or type(spec['max']) is not int or not -2_000_000 <= spec['min'] <= spec['max'] <= 2_000_000:
                raise ValueError('Invalid integer range')
            samples[name] = spec['min']
        elif kind == 'choice':
            if not isinstance(spec['choices'], list) or not 1 <= len(spec['choices']) <= 32:
                raise ValueError('Provide 1..32 choices')
            for value in spec['choices']:
                checked_value(spec, value, tools)
            samples[name] = spec['choices'][0]
        else:
            samples[name] = 'example.txt'
    bind(template, samples, tools)


class WorkflowInputs:
    def __init__(self, memory: Memory, workspace: str | Path) -> None:
        self.memory = memory
        self.tools = Tools(workspace)
        self.workspace = str(self.tools.root)
        self.db = memory.db
        self.db.execute('''CREATE TABLE IF NOT EXISTS workflow_inputs (
            id TEXT PRIMARY KEY, workspace TEXT NOT NULL, template TEXT NOT NULL,
            inputs TEXT NOT NULL, status TEXT NOT NULL, workflow_id TEXT)''')
        self.db.commit()

    def start(self, template: dict) -> dict:
        validate_template(template, self.tools)
        key = uuid.uuid4().hex
        with self.db:
            self.db.execute('INSERT INTO workflow_inputs VALUES(?,?,?,?,?,?)',
                            (key, self.workspace, packed(template), '{}', 'collecting', None))
        return self.get(key)

    def list(self) -> list[dict]:
        return [self.get(row[0]) for row in self.db.execute(
            'SELECT id FROM workflow_inputs WHERE workspace=? ORDER BY rowid DESC LIMIT 100',
            (self.workspace,))]

    def get(self, key: str) -> dict:
        row = self.db.execute('SELECT * FROM workflow_inputs WHERE id=? AND workspace=?',
                              (key, self.workspace)).fetchone()
        if row is None:
            raise ValueError('Unknown input draft in this workspace')
        result = dict(row)
        result['template'] = json.loads(result['template'])
        result['inputs'] = json.loads(result['inputs'])
        missing = [name for name in result['template']['inputs'] if name not in result['inputs']]
        result['missing'] = missing if result['status'] == 'collecting' else []
        result['next_question'] = ({'name': missing[0], **result['template']['inputs'][missing[0]]}
                                   if missing and result['status'] == 'collecting' else None)
        return result

    def set(self, key: str, values: dict) -> dict:
        record = self.get(key)
        if record['status'] != 'collecting':
            raise ValueError('Only collecting drafts accept corrections; start a new draft')
        specs = record['template']['inputs']
        if not isinstance(values, dict) or not values or set(values) - set(specs):
            raise ValueError('Provide declared input names only')
        updated = dict(record['inputs'])
        for name, value in values.items():
            updated[name] = checked_value(specs[name], value, self.tools)
        if set(updated) == set(specs):
            bind(record['template'], updated, self.tools)
        with self.db:
            self.db.execute("UPDATE workflow_inputs SET inputs=? WHERE id=? AND status='collecting'",
                            (packed(updated), key))
        return self.get(key)

    def cancel(self, key: str) -> dict:
        record = self.get(key)
        if record['status'] != 'collecting':
            raise ValueError('Only collecting drafts can be cancelled')
        with self.db:
            self.db.execute("UPDATE workflow_inputs SET status='cancelled',inputs='{}' WHERE id=?", (key,))
        return self.get(key)

    def prepare(self, key: str) -> dict:
        record = self.get(key)
        if record['status'] == 'prepared':
            return record
        if record['status'] != 'collecting' or record['missing']:
            raise ValueError('Collect all inputs before preparing a workflow')
        plan = bind(record['template'], record['inputs'], self.tools)
        workflow = Workflows(self.memory, self.workspace).propose(plan)
        with self.db:
            self.db.execute("UPDATE workflow_inputs SET status='prepared',workflow_id=? WHERE id=?",
                            (workflow['id'], key))
        return self.get(key)
