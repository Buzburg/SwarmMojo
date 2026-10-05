"""Hardware throttling, concurrency queueing, and resource protection for multi-agent execution."""

import asyncio
import os
import sys
import psutil
from functools import wraps
from typing import Callable, Any, Optional

from app.config import (
    MAX_CONCURRENT_TASKS,
    MAX_CPU_PERCENT,
    MIN_AVAILABLE_RAM_MB,
)


class HardwareThrottle:
    """Protects host CPU and RAM from multi-agent swarms using asyncio semaphore and psutil backoff."""

    def __init__(
        self,
        max_concurrent: int = MAX_CONCURRENT_TASKS,
        max_cpu_percent: float = MAX_CPU_PERCENT,
        min_available_ram_mb: float = MIN_AVAILABLE_RAM_MB,
    ):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.max_cpu = max_cpu_percent
        self.min_ram = min_available_ram_mb
        # Prime psutil non-blocking baseline
        psutil.cpu_percent(interval=None)

    async def wait_for_headroom(
        self, timeout: float = 45.0, check_interval: float = 1.0
    ) -> None:
        """Yields execution until the host drops below safe hardware thresholds."""
        loop = asyncio.get_running_loop()
        start = loop.time()
        while True:
            # interval=None provides an instantaneous non-blocking sample
            cpu = psutil.cpu_percent(interval=None)
            avail_ram = psutil.virtual_memory().available / (1024 * 1024)

            if cpu < self.max_cpu and avail_ram > self.min_ram:
                return

            if loop.time() - start > timeout:
                raise TimeoutError(
                    f"Resource contention timeout: Host stayed at {cpu:.1f}% CPU "
                    f"and {avail_ram:.0f}MB free RAM for {timeout}s."
                )
            await asyncio.sleep(check_interval)

    def guard(self, timeout: float = 45.0):
        """Decorator to wrap async FastMCP tool handlers."""

        def decorator(func: Callable[..., Any]):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Bound queue waiting separately from the resource backoff.
                await asyncio.wait_for(self.semaphore.acquire(), timeout=timeout)
                try:
                    # 2. Back off if host is currently spiking above threshold
                    await self.wait_for_headroom(timeout=timeout)
                    # 3. Execute the tool
                    if asyncio.iscoroutinefunction(func):
                        return await func(*args, **kwargs)
                    return func(*args, **kwargs)
                finally:
                    self.semaphore.release()

            return wrapper

        return decorator


def get_process_preexec_fn() -> Optional[Callable[[], None]]:
    """Returns lower_priority function for Unix or None for Windows platforms."""
    if sys.platform == "win32":
        return None

    def lower_priority():
        try:
            if hasattr(os, "nice"):
                os.nice(10)
        except (AttributeError, OSError):
            pass

    return lower_priority


# Singleton limiter instance configured for workstation agent setups
tool_limiter = HardwareThrottle()
