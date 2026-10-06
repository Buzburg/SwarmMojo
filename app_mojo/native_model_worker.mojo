"""One owned native model request. Parent cancellation terminates this process."""
from std.ffi import c_int, external_call
from std.python import Python
from std.sys import argv
from app_mojo.rwkv_engine import RWKV7Session


def main() raises:
    # Set parent-death handling before loading Python or the model; close the race.
    if external_call["prctl", c_int](c_int(1), c_int(9), UInt(0), UInt(0), UInt(0)) != 0:
        raise Error("Cannot establish native worker parent ownership")
    var args = argv()
    if len(args) != 2 or Int(args[1]) != Int(external_call["getppid", c_int]()):
        raise Error("Native worker parent changed")
    var helper = Python.import_module("app.native_model_worker")
    var request = helper.read_request(args[0])
    var session = RWKV7Session(String(request[0]), 4096, 4)
    session.answer_format()
    _ = helper.write_ready(request[3])
    session.prefill(String(request[1]))
    var builtins = Python.import_module("builtins")
    var output = builtins.bytearray()
    var bytes = 0
    var tokens = 0
    var ended = False
    for _ in range(Int(py=request[2])):
        var next = session.next_piece()
        if next[0]:
            ended = True
            break
        for byte in next[1]:
            bytes += 1
            if bytes > 12000:
                raise Error("Native output exceeded its byte budget")
            _ = output.append(Int(byte))
        tokens += 1
    session.close()
    _ = helper.write_response(output, ended, request[3], tokens)
