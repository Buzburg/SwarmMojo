"""Bounded asynchronous actions; native Mojo retains all broker socket ownership."""
import asyncio
from dataclasses import dataclass
import json
import os

import httpx

from app import broker_actions as actions, broker_protocol as protocol, broker_requests
from app.json_protocol import unique_object
from app.task_worker_client import async_request as worker_request

MAX_JOBS = 16
MAX_LANE_REQUESTS = 5  # One active request plus four queued requests per lane.
QUEUE_TIMEOUT = 5.0


async def gateway(path: str, body: dict | None = None, *, timeout: float = 120) -> dict:
    headers = {'Authorization': 'Bearer ' + os.environ['ROMS_GATEWAY_API_KEY']} if os.getenv('ROMS_GATEWAY_API_KEY') else {}
    port = int(os.getenv('ROMS_GATEWAY_PORT', '8844'))
    async with asyncio.timeout(timeout), httpx.AsyncClient(trust_env=False, timeout=timeout) as client:
        async with client.stream('POST' if body is not None else 'GET', f'http://127.0.0.1:{port}' + path,
                                 json=body, headers=headers) as response:
            response.raise_for_status()
            data = bytearray()
            async for part in response.aiter_bytes():
                data.extend(part)
                if len(data) > protocol.MAX_FRAME:
                    raise protocol.ProtocolError('RESPONSE_TOO_LARGE', 'Gateway response exceeds the broker limit')
    value = json.loads(data, object_pairs_hook=unique_object)
    if type(value) is not dict:
        raise ValueError('Invalid gateway response')
    return value


async def dispatch(request: dict, frame: bytearray, legacy: bool) -> str:
    action, args = request['action'], request['args']
    request_id = request['id']
    if action in {'status', 'rwkv_status'}:
        health, worker = await asyncio.gather(gateway('/health', timeout=3), worker_request('ping', timeout=1),
                                               return_exceptions=True)
        result = actions.status_result(health if type(health) is dict else {},
                                      type(worker) is dict and worker.get('ok') is True and worker.get('result') == 'pong')
    elif action == 'memory.search':
        from app.broker_memory import search
        result = {'ok': True, 'result': await search(args)}
    elif action == 'chat':
        response = await gateway('/v1/chat/completions', {'messages': [{'role': 'user', 'content': args['prompt']}],
                                                        'max_tokens': 256, 'stream': False, 'temperature': 0.3})
        result = {'ok': True, 'result': response['choices'][0]['message']['content']}
    elif action == 'task.validate':
        async def validate() -> str:
            return actions.encode_result(await worker_request(action, args), request_id)
        return await broker_requests.execute_async(request, validate)
    elif action in {'task.status', 'worker_status', 'worker_recovery'}:
        name = {'worker_status': 'capabilities', 'worker_recovery': 'recovery'}.get(action, action)
        result = await worker_request(name, args, timeout=45 if action == 'worker_status' else 5)
    else:
        return actions.handle(frame)
    return actions.encode_result(result, request_id, legacy=legacy)


@dataclass
class Job:
    task: asyncio.Task[str]
    durable: bool
    detached: bool = False


class Scheduler:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.jobs: dict[int, Job] = {}
        self.next_token = 1
        self.gates = {lane: asyncio.Semaphore(1) for lane in ('chat', 'validation', 'memory')}
        self.counts = {lane: 0 for lane in self.gates}

    def submit(self, frame: bytearray) -> tuple[int, str]:
        request_id = None
        legacy = bytes(frame) in {b'PING', b'STATUS'}
        try:
            request = ({'v': 1, 'id': None, 'action': bytes(frame).decode().lower(), 'args': {}} if legacy else
                       protocol.parse(bytes(frame)))
            request_id = request['id']
            actions.validate_action(request['action'], request['args'])
            if request['action'] == 'task.validate':
                cached = broker_requests.replay(request)
                if cached is not None:
                    return -1, cached
            lane = ('memory' if request['action'] == 'memory.search' else
                    'chat' if request['action'] == 'chat' else
                    'validation' if request['action'] in {'task.validate', 'worker_status'} else None)
            if len(self.jobs) >= MAX_JOBS or (lane and self.counts[lane] >= MAX_LANE_REQUESTS):
                raise protocol.ProtocolError('QUEUE_FULL', 'The broker is at capacity; retry later')
            if lane:
                self.counts[lane] += 1
            token = self.next_token
            self.next_token += 1
            task = self.loop.create_task(self.run(request, frame, legacy, lane, self.loop.time() + QUEUE_TIMEOUT))
            if lane:
                def release_count(_: asyncio.Task) -> None:
                    self.counts[lane] -= 1
                task.add_done_callback(release_count)
            self.jobs[token] = Job(task, request['action'] == 'task.validate')
            return token, ''
        except protocol.ProtocolError as error:
            return -1, protocol.encode(protocol.error_response(error.code, str(error), request_id))
        except (ValueError, TypeError):
            return -1, protocol.encode(protocol.error_response('INVALID_REQUEST', 'Arguments do not match the action contract', request_id))

    async def run(self, request: dict, frame: bytearray, legacy: bool, lane: str | None, queue_deadline: float) -> str:
        acquired = False
        dispatched = False
        try:
            if lane:
                try:
                    if self.loop.time() >= queue_deadline:
                        raise TimeoutError
                    async with asyncio.timeout_at(queue_deadline):
                        await self.gates[lane].acquire()
                    acquired = True
                except TimeoutError:
                    raise protocol.ProtocolError('QUEUE_TIMEOUT', 'The broker queue deadline expired; no action was dispatched') from None
            dispatched = True
            async with asyncio.timeout(180 if request['action'] == 'task.validate' else 120):
                return await dispatch(request, frame, legacy)
        except protocol.ProtocolError as error:
            return protocol.encode(protocol.error_response(error.code, str(error), request['id']))
        except (TimeoutError, httpx.TimeoutException):
            code = 'REQUEST_UNCERTAIN' if dispatched and request['action'] == 'task.validate' else 'REQUEST_TIMEOUT'
            return protocol.encode(protocol.error_response(code, 'The local action deadline expired; inspect the task before retrying validation', request['id']))
        except (OSError, httpx.HTTPError, ValueError, TypeError, KeyError, IndexError, RecursionError):
            return actions.encode_result({'ok': False, 'error': 'service_unavailable'}, request['id'], legacy=legacy)
        finally:
            if acquired:
                self.gates[lane].release()

    def tick(self) -> None:
        self.loop.run_until_complete(asyncio.sleep(0))
        for token, job in list(self.jobs.items()):
            if job.detached and job.task.done():
                if not job.task.cancelled():
                    job.task.result()
                del self.jobs[token]

    def ready(self, token: int) -> bool:
        return self.jobs[token].task.done()

    def take(self, token: int) -> str:
        return self.jobs.pop(token).task.result()

    def detach(self, token: int) -> None:
        job = self.jobs[token]
        job.detached = True
        if not job.durable and not job.task.done():
            job.task.cancel()

    def close(self) -> None:
        for job in self.jobs.values():
            job.task.cancel()
        async def settle() -> None:
            await asyncio.gather(*(job.task for job in self.jobs.values()), return_exceptions=True)
        self.loop.run_until_complete(settle())
        self.jobs.clear()
        self.loop.close()
