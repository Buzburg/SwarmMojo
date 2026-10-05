"""Queue and cancellation regressions without launching tools."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from app.throttle import HardwareThrottle


def test_queue_timeout_and_cancel_release_capacity():
    async def scenario():
        limiter = HardwareThrottle(max_concurrent=1)
        limiter.wait_for_headroom = AsyncMock()
        started = asyncio.Event()
        release = asyncio.Event()

        @limiter.guard(timeout=0.05)
        async def work():
            started.set()
            await release.wait()
            return "done"

        first = asyncio.create_task(work())
        await started.wait()
        with pytest.raises(TimeoutError):
            await work()
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        release.set()
        assert await work() == "done"

    asyncio.run(scenario())


def test_mcp_handler_has_only_one_limiter_boundary(monkeypatch):
    monkeypatch.delenv('ROMS_ENABLE_EXPERIMENTAL_EXECUTION', raising=False)
    # Exercise the registered tool's underlying function, including its delegate.
    from app import server, tools
    async def scenario():
        original = tools.tool_limiter.semaphore
        original_wait = tools.tool_limiter.wait_for_headroom
        tools.tool_limiter.semaphore = asyncio.Semaphore(1)
        tools.tool_limiter.wait_for_headroom = AsyncMock()
        try:
            handler = server.run_sandboxed_command
            handler = getattr(handler, "fn", handler)
            result = await asyncio.wait_for(handler(image="unused", command="unused"), 1)
            assert "disabled" in result
        finally:
            tools.tool_limiter.semaphore = original
            tools.tool_limiter.wait_for_headroom = original_wait
    asyncio.run(scenario())
