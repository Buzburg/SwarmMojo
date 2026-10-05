"""Bind Mojo handlers as Python callables for the FastMCP transport."""
from std.python import Python, PythonObject
from std.python.bindings import PythonModuleBuilder
from app_mojo.db import init_database
from app_mojo.context_bindings import pack_context
from app_mojo.okf_loader import ingest_okf_directory
from app_mojo.rag_engine import search_knowledge_base
from app_mojo.tools import create_support_ticket, get_support_ticket, update_ticket_status, list_support_tickets

def _search(query: PythonObject, limit: PythonObject) raises -> PythonObject:
    return PythonObject(search_knowledge_base(String(query), Int(py=limit), Python.none()))

def _create(ticket: PythonObject, email: PythonObject, summary: PythonObject) raises -> PythonObject:
    return PythonObject(create_support_ticket(String(ticket), String(email), String(summary), Python.none()))

def _get(ticket: PythonObject) raises -> PythonObject:
    return PythonObject(get_support_ticket(String(ticket), Python.none()))

def _update(ticket: PythonObject, status: PythonObject) raises -> PythonObject:
    return PythonObject(update_ticket_status(String(ticket), String(status), Python.none()))

def _list(status: PythonObject) raises -> PythonObject:
    return PythonObject(list_support_tickets(String(status), Python.none()))

def build_native_module() raises -> PythonObject:
    var builder = PythonModuleBuilder("roms_native")
    builder.def_function[pack_context]("pack_context")
    builder.def_function[_search]("search_knowledge_base")
    builder.def_function[_create]("create_support_ticket")
    builder.def_function[_get]("get_support_ticket")
    builder.def_function[_update]("update_ticket_status")
    builder.def_function[_list]("list_support_tickets")
    return builder.finalize()

def start_mojo_server() raises:
    var sys = Python.import_module("sys")
    sys.stderr.write("[ROMS-Mojo] Initializing database and knowledge...\n")
    init_database(Python.none())
    # Supplemental Python tools need the shared trajectory/tool-registry schema.
    var database = Python.import_module("app.db")
    database.init_database()
    var registry = Python.import_module("app.tool_rag")
    registry.init_default_tool_registry()
    var count = ingest_okf_directory(Python.none(), Python.none())
    sys.stderr.write("[ROMS-Mojo] Indexed " + String(count) + " documents. Starting MCP.\n")
    var native = build_native_module()
    var bridge = Python.import_module("app.mojo_bridge")
    var server = bridge.build_server(native)
    server.run()
