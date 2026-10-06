"""Ephemeral operations release resources on disconnect and cancellation."""
import asyncio

import pytest
from starlette.requests import Request

from app.request_lifecycle import ClientDisconnected, while_connected


def test_already_disconnected_client_never_starts_work():
    async def check():
        async def receive():
            return {'type': 'http.disconnect'}
        async def unexpected():
            pytest.fail('Disconnected client started work')
        with pytest.raises(ClientDisconnected):
            await while_connected(Request({'type': 'http'}, receive), unexpected)
    asyncio.run(check())


@pytest.mark.parametrize('failure', [False, True])
def test_result_or_error_settles_receive_watcher(failure):
    async def check():
        stopped = asyncio.Event()
        async def receive():
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
        async def operation():
            if failure:
                raise ValueError('Fixture failure')
            return 'result'
        request = Request({'type': 'http'}, receive)
        if failure:
            with pytest.raises(ValueError, match='Fixture failure'):
                await while_connected(request, operation)
        else:
            assert await while_connected(request, operation) == 'result'
        assert stopped.is_set()
    asyncio.run(check())


def test_repeated_parent_cancellation_waits_for_resource_cleanup():
    async def check():
        started, cleaning, release, closed = (asyncio.Event() for _ in range(4))
        async def receive():
            await asyncio.Event().wait()
        async def operation():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaning.set()
                await release.wait()
                closed.set()
        task = asyncio.create_task(while_connected(Request({'type': 'http'}, receive), operation))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        await asyncio.wait_for(cleaning.wait(), 1)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        assert closed.is_set()
    asyncio.run(check())
