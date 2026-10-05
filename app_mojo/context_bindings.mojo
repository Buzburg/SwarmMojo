"""Convert once at the boundary, then run the native selector."""
from std.python import Python, PythonObject
from app_mojo.context_select import select_context

def pack_context(costs: PythonObject, utilities: PythonObject, budget: PythonObject, required: PythonObject) raises -> PythonObject:
    var n = len(costs)
    if n > 64 or n != len(utilities):
        raise Error("Invalid context selector dimensions")
    var native_costs = List[Int](capacity=n)
    var native_utilities = List[Int](capacity=n)
    for i in range(n):
        native_costs.append(Int(py=costs[i]))
        native_utilities.append(Int(py=utilities[i]))
    var picked = select_context(native_costs, native_utilities, Int(py=budget), Int(py=required))
    var builtins = Python.import_module("builtins")
    var result = builtins.list()
    for i in range(len(picked)):
        result.append(picked[i])
    return result
