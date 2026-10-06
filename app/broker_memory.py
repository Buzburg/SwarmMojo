"""Read project lessons through the existing ROMS MCP schema and owned stdio service."""
import asyncio
import json
import os
from pathlib import Path
import re
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from app import broker_protocol as protocol
from app.json_protocol import unique_object
from app.request_lifecycle import cancel_and_settle

TIMEOUT = 20.0
ROOT = Path(__file__).resolve().parents[1]


def validate_args(args: dict) -> None:
    if not {'project_id', 'query'} <= set(args) or set(args) - {
        'project_id', 'query', 'limit', 'max_chars', 'include_candidates', 'revision'
    }:
        raise ValueError('memory.search requires a project ID and query')
    project = args['project_id']
    if not isinstance(project, str) or not 1 <= len(project) <= 128 or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/-]*', project):
        raise ValueError('Invalid project ID')
    for name, maximum in [('query', 500), ('revision', 160)]:
        value = args.get(name, '')
        if not isinstance(value, str) or len(value) > maximum or '\x00' in value:
            raise ValueError('Invalid search text')
    for name, default, lower, upper in [('limit', 5, 1, 20), ('max_chars', 6000, 500, 12000)]:
        value = args.get(name, default)
        if type(value) is not int or not lower <= value <= upper:
            raise ValueError('Invalid search bound')
    if type(args.get('include_candidates', False)) is not bool:
        raise ValueError('Invalid candidate filter')


def parameters() -> StdioServerParameters:
    # SDK inheritance is limited to basic POSIX process variables. Forward only
    # the local Python runtime and database location, never model/API secrets.
    env = {name: os.environ[name] for name in
           ('PYTHONHOME', 'LD_LIBRARY_PATH', 'ROMS_DATA_DIR', 'ROMS_DB_PATH') if name in os.environ}
    env.update(PYTHONPATH=str(ROOT), PYTHONNOUSERSITE='1', ROMS_ENABLE_EXPERIMENTAL_EXECUTION='0')
    prefix = Path(os.getenv('ROMS_PYTHON_PREFIX', sys.prefix))
    return StdioServerParameters(command=str(prefix / 'bin/python'), args=['-m', 'app.memory_service'],
                                 env=env, cwd=str(ROOT))


def response_value(response, max_chars: int) -> dict:
    response = response.model_dump(by_alias=True)
    if response.get('isError') or len(response['content']) != 1 or response['content'][0]['type'] != 'text':
        raise ValueError('Memory service did not return one successful text result')
    raw = response['content'][0]['text']
    if len(raw) > max_chars or len(raw.encode()) > 48000:
        raise protocol.ProtocolError('RESPONSE_TOO_LARGE', 'Memory response exceeds the requested bound')
    value = json.loads(raw, object_pairs_hook=unique_object)
    if type(value) is not dict:
        raise ValueError('Invalid memory response')
    return value


def decode_result(response, args: dict) -> dict:
    value = response_value(response, args.get('max_chars', 6000))
    if type(value) is not dict or set(value) != {'memories', 'truncated'} or type(value['truncated']) is not bool:
        raise ValueError('Invalid memory result')
    records = value['memories']
    if type(records) is not list or len(records) > args.get('limit', 5):
        raise ValueError('Invalid memory inventory')
    for record in records:
        if (type(record) is not dict or record.get('project_id') != args['project_id'] or
                not isinstance(record.get('id'), str) or not isinstance(record.get('source_ref'), str) or
                not isinstance(record.get('summary'), str) or record.get('status') not in {'candidate', 'verified'} or
                record.get('outcome') not in {'unknown', 'success', 'failure'} or
                type(record.get('recommendation_eligible')) is not bool or
                (record['status'] == 'candidate' and not args.get('include_candidates', False))):
            raise ValueError('Invalid or cross-project memory record')
    return value


def decode_context(response, args: dict) -> dict:
    value = response_value(response, args['max_chars'])
    fields = {'project_id', 'backend', 'selection', 'evidence_authority', 'pool_truncated',
              'candidates', 'duplicates_removed', 'omitted', 'warning_available', 'warning_included', 'records'}
    if (set(value) != fields or value['project_id'] != args['project_id'] or value['backend'] != 'python' or
            value['selection'] != 'rank-utility-knapsack-v1' or value['evidence_authority'] != 'caller-supplied' or
            any(type(value[key]) is not bool for key in ('pool_truncated', 'warning_available', 'warning_included')) or
            any(type(value[key]) is not int or not 0 <= value[key] <= 20
                for key in ('candidates', 'duplicates_removed', 'omitted')) or
            type(value['records']) is not list or len(value['records']) > 20):
        raise ValueError('Invalid project context envelope')
    for row in value['records']:
        if (type(row) is not dict or set(row) != {'id', 'summary', 'source_ref', 'revision', 'expires_at',
                                                'outcome', 'role', 'retrieval_rank', 'verification'} or
                any(not isinstance(row.get(key), str) for key in ('id', 'summary', 'source_ref', 'revision')) or
                (row['expires_at'] is not None and not isinstance(row['expires_at'], str)) or
                row.get('outcome') not in {'success', 'failure'} or
                row.get('role') != ('warning' if row['outcome'] == 'failure' else 'lesson') or
                type(row.get('retrieval_rank')) is not int or not 1 <= row['retrieval_rank'] <= 20 or
                type(row.get('verification')) is not dict or
                not isinstance(row['verification'].get('evidence_ref'), str) or
                row['verification'].get('authority') != 'caller-supplied' or
                type(row['verification'].get('exit_code')) is not int or
                (row['verification']['exit_code'] == 0) != (row['outcome'] == 'success')):
            raise ValueError('Invalid project context record')
    if (value['warning_included'] != any(row['role'] == 'warning' for row in value['records']) or
            (value['warning_included'] and not value['warning_available']) or
            len(value['records']) + value['omitted'] + value['duplicates_removed'] != value['candidates']):
        raise ValueError('Inconsistent project context selection')
    return value


async def lookup(args: dict, *, context: bool = False) -> dict:
    tool_name = 'memory_prepare_context' if context else 'memory_recall'
    async with stdio_client(parameters()) as (read, write):
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            if initialized.model_dump(by_alias=True)['serverInfo']['name'] != 'ROMS-Memory':
                raise ValueError('Unexpected memory server')
            listing = (await session.list_tools()).model_dump(by_alias=True)
            tools = [tool for tool in listing['tools'] if tool['name'] == tool_name]
            if len(tools) != 1 or listing.get('nextCursor'):
                raise ValueError('Memory discovery is incomplete')
            schema = tools[0]['inputSchema']
            if schema.get('type') != 'object' or not {'project_id', 'query'} <= set(schema.get('required', [])):
                raise ValueError('Incompatible memory schema')
            response = await session.call_tool(tool_name, args)
    return decode_context(response, args) if context else decode_result(response, args)


async def search(args: dict, *, context: bool = False) -> dict:
    validate_args(args)
    if context and (set(args) != {'project_id', 'query', 'max_chars', 'revision'} or
                    not 1024 <= args['max_chars'] <= 12000):
        raise ValueError('Invalid context lookup arguments')
    work = asyncio.create_task(lookup(args, context=True) if context else lookup(args))
    try:
        try:
            async with asyncio.timeout(TIMEOUT):
                return await asyncio.shield(work)
        finally:
            await cancel_and_settle([work])
    except TimeoutError:
        raise protocol.ProtocolError('REQUEST_TIMEOUT', 'The memory lookup deadline expired') from None
    except protocol.ProtocolError:
        raise
    except Exception as error:
        # This boundary also catches SDK task-group failures without exposing
        # child diagnostics, paths or credentials in protocol replies.
        raise protocol.ProtocolError('SERVICE_UNAVAILABLE', 'The local memory service could not complete the lookup') from error
