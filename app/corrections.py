"""Turn supplied corrections into inactive regression proposals, never approval."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from app import memory


def _draft(proposal: dict[str, object], fingerprint: str, status: str) -> str:
    lines = [
        '---', 'draft_status: "inactive"', f'lesson_status: "{status}"',
        f'fingerprint: "{fingerprint}"', '---', '',
        '# Proposed regression control', '',
        'Untrusted, caller-supplied proposal. No check was run, evidence authenticated,',
        'action approved, or skill activated by this operation.', '',
    ]
    for title, field in (('Project', 'project_id'), ('Revision', 'revision'),
                         ('Observed failure', 'failure'), ('Proposed correction', 'correction'),
                         ('Proposed regression check', 'proposed_check')):
        lines.extend(['## ' + title, '', *('    ' + line for line in str(proposal[field]).splitlines()), ''])
    lines.extend(['## Supplied evidence references', '',
                  *('    ' + line for line in json.dumps(proposal['evidence'], ensure_ascii=True, indent=2).splitlines()), '',
                  'Review the exact revision and evidence, implement the accepted check in the',
                  'existing workshop, and record its actual result separately. This draft grants no permission.', ''])
    return '\n'.join(lines)


def propose_correction(
    project_id: str, failure: str, correction: str, proposed_check: str,
    revision: str, evidence: list[dict[str, str]], session_id: str = '', *,
    db_path: Path | str | None = None,
) -> dict[str, object]:
    """Save one scoped candidate with an inactive Markdown draft returned as text.

    Evidence references and hashes are caller-supplied, never opened or authenticated.
    The complete normalized payload identifies exact retries, including after restart.
    Existing verified, retracted or superseded records are returned without revival.
    """
    project = memory._scope(project_id)
    proposal: dict[str, object] = {
        'schema': 'swarmmojo.correction/v1', 'project_id': project,
        'failure': memory._text(failure, 'failure', 1000),
        'correction': memory._text(correction, 'correction', 1000),
        'proposed_check': memory._text(proposed_check, 'proposed_check', 1000),
        'revision': memory._text(revision, 'revision', 160),
        'session_id': memory._text(session_id, 'session_id', 128, required=False),
    }
    if type(evidence) is not list or not 1 <= len(evidence) <= 4:
        raise ValueError('evidence must contain 1–4 reference/hash objects')
    references: list[dict[str, str]] = []
    for entry in evidence:
        if type(entry) is not dict or set(entry) != {'ref', 'sha256'}:
            raise ValueError('Each evidence item must contain exactly ref and sha256')
        reference = memory._text(entry['ref'], 'evidence ref', 1000)
        checksum = entry['sha256']
        if type(checksum) is not str or not re.fullmatch(r'[a-fA-F0-9]{64}', checksum):
            raise ValueError('Evidence sha256 must be 64 hexadecimal characters')
        references.append({'ref': reference, 'sha256': checksum.lower()})
    proposal['evidence'] = references
    serialized = json.dumps(proposal, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    try:
        fingerprint = hashlib.sha256(serialized.encode('utf-8')).hexdigest()
    except UnicodeEncodeError as error:
        raise ValueError('Proposal text must be valid UTF-8') from error
    memory_id = 'correction-' + fingerprint
    summary = '\n'.join((f"Observed failure: {proposal['failure']}",
                         f"Proposed correction: {proposal['correction']}",
                         f"Proposed regression: {proposal['proposed_check']}"))
    with memory._connection(db_path) as connection:
        connection.execute('BEGIN IMMEDIATE')
        existing = connection.execute('SELECT id FROM lesson_memories WHERE id = ?', (memory_id,)).fetchone()
        if existing is None:
            connection.execute(
                "INSERT INTO lesson_memories(id, project_id, summary, source_ref, revision, session_id, "
                "status, outcome, created_at) VALUES (?, ?, ?, ?, ?, ?, 'candidate', 'unknown', ?)",
                (memory_id, project, summary, 'correction://' + fingerprint,
                 proposal['revision'], proposal['session_id'], memory._now()),
            )
            memory._event(connection, memory_id, 'retained', 'Correction proposal; no verification recorded')
            memory._event(connection, memory_id, 'correction_proposal', serialized)
        record = memory._record(memory._find(connection, project, memory_id))
    return {
        'schema': 'swarmmojo.correction-proposal/v1', 'fingerprint': fingerprint,
        'memory': record, 'proposal': proposal, 'deduplicated': existing is not None,
        'draft_markdown': _draft(proposal, fingerprint, str(record['status'])),
        'evidence_authority': 'caller-supplied', 'evidence_authenticated': False,
        'regression_status': 'not-run', 'draft_active': False,
        'execution_allowed': False, 'approval_required': True,
    }
