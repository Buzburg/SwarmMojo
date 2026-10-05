"""Run parity and benchmark checks through the real Python/Mojo boundary."""
from std.python import Python
from std.python.bindings import PythonModuleBuilder
from app_mojo.context_bindings import pack_context

def main() raises:
    var builder = PythonModuleBuilder("roms_context_bench")
    builder.def_function[pack_context]("pack_context")
    var native = builder.finalize()
    var benchmark = Python.import_module("benchmarks.bench_context")
    benchmark.run(native.pack_context)
