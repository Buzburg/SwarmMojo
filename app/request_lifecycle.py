"""Cancel ephemeral HTTP work when its fully read request disconnects."""
import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from starlette.requests import Request

T = TypeVar('T')


class ClientDisconnected(Exception):
    pass


async def while_connected(request: Request, operation: Callable[[], Awaitable[T]]) -> T:
    """Call only after consuming the request body; own and settle both tasks."""
    async def disconnected() -> None:
        while (await request.receive())['type'] != 'http.disconnect':
            pass

    watcher = asyncio.create_task(disconnected())
    work = None
    try:
        # Observe an already queued disconnect before starting upstream work.
        await asyncio.sleep(0)
        if watcher.done():
            watcher.result()
            raise ClientDisconnected
        work = asyncio.create_task(operation())
        done, _ = await asyncio.wait({watcher, work}, return_when=asyncio.FIRST_COMPLETED)
        if watcher in done:
            watcher.result()
            raise ClientDisconnected
        return work.result()
    finally:
        pending = [task for task in (watcher, work) if task is not None]
        for task in pending:
            if not task.done():
                task.cancel()
        cleanup = asyncio.gather(*pending, return_exceptions=True)
        cancelled_again = False
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                cancelled_again = True
        if cancelled_again:
            raise asyncio.CancelledError
