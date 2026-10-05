"""Mojo Hardware Throttling and Concurrency Guard.

Protects host CPU and RAM from multi-agent tool swarms, ensuring the local LLM
inference engine (e.g. Ollama, llama.cpp, vLLM) never experiences token latency spikes
or GPU memory paging crashes.
"""

from std.python import Python
from app_mojo.config import ROMSConfig

struct MojoThrottle:
    var max_concurrent: Int
    var max_cpu_percent: Float64
    var min_available_ram_mb: Float64

    def __init__(out self):
        var cfg = ROMSConfig()
        self.max_concurrent = cfg.max_concurrent
        self.max_cpu_percent = cfg.max_cpu_percent
        self.min_available_ram_mb = cfg.min_ram_mb

    def check_headroom(self) raises -> Bool:
        """Checks if host CPU and available RAM are within safe thresholds."""
        var psutil = Python.import_module("psutil")
        var cpu = float(psutil.cpu_percent(interval=None))
        var avail_mb = float(psutil.virtual_memory().available / (1024 * 1024))
        return cpu < self.max_cpu_percent and avail_mb > self.min_available_ram_mb

    def wait_for_headroom(self, timeout: Float64 = 30.0, check_interval: Float64 = 0.5) raises:
        """Yields execution until the host drops below safe hardware thresholds.

        Prevents running heavy tools while the local LLM is actively prefilling or generating.
        """
        var psutil = Python.import_module("psutil")
        var time = Python.import_module("time")
        var start = time.time()

        while True:
            var cpu = float(psutil.cpu_percent(interval=None))
            var avail_mb = float(psutil.virtual_memory().available / (1024 * 1024))

            if cpu < self.max_cpu_percent and avail_mb > self.min_available_ram_mb:
                return

            if time.time() - start > timeout:
                return  # Fallthrough safely to avoid permanently stalling agent loops

            time.sleep(check_interval)
