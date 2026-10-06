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


def decode_result(response, args: dict) -> dict:
    response = response.model_dump(by_alias=True)
    if response.get('isError') or len(response['content']) != 1 or response['content'][0]['type'] != 'text':
        raise ValueError('Memory service did not return one successful text result')
    raw = response['content'][0]['text']
    if len(raw) > args.get('max_chars', 6000) or len(raw.encode()) > 48000:
        raise protocol.ProtocolError('RESPONSE_TOO_LARGE', 'Memory response exceeds the requested bound')
    value = json.loads(raw, object_pairs_hook=unique_object)
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


async def lookup(args: dict) -> dict:
    async with stdio_client(parameters()) as (read, write):
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            if initialized.model_dump(by_alias=True)['serverInfo']['name'] != 'ROMS-Memory':
                raise ValueError('Unexpected memory server')
            listing = (await session.list_tools()).model_dump(by_alias=True)
            tools = [tool for tool in listing['tools'] if tool['name'] == 'memory_recall']
            if len(tools) != 1 or listing.get('nextCursor'):
                raise ValueError('Memory discovery is incomplete')
            schema = tools[0]['inputSchema']
            if schema.get('type') != 'object' or not {'project_id', 'query'} <= set(schema.get('required', [])):
                raise ValueError('Incompatible memory schema')
            response = await session.call_tool('memory_recall', args)
    return decode_result(response, args)


async def search(args: dict) -> dict:
    validate_args(args)
    work = asyncio.create_task(lookup(args))
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
