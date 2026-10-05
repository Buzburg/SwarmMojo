"""Mojo OKF Markdown & Universal Document Ingestion Engine."""

from std.python import Python, PythonObject
from app_mojo.config import get_base_paths


def _ensure_python_path() raises:
    """Ensures workspace root is in Python sys.path so app modules import cleanly in WSL."""
    var sys = Python.import_module("sys")
    var os = Python.import_module("os")
    var cwd = os.getcwd()
    if not sys.path.__contains__(cwd):
        sys.path.insert(0, cwd)



def ingest_okf_file(filepath: PythonObject, custom_db_path: PythonObject = Python.none()) raises -> Bool:
    """Ingests a single OKF document or dataset file (.md, .csv, .json, etc.) with SHA-256 deduplication."""
    _ensure_python_path()
    var app_okf = Python.import_module("app.okf_loader")
    var res = app_okf.ingest_document_file(filepath, custom_db_path)
    return res.__bool__()


def ingest_okf_directory(custom_dir: PythonObject = Python.none(), custom_db_path: PythonObject = Python.none()) raises -> Int:
    """Scans directory and ingests all changed or new knowledge files."""
    _ensure_python_path()
    var paths = get_base_paths()
    var is_none = Python.evaluate("lambda x: x is None")(custom_dir)
    var target_dir = paths[2] if is_none else custom_dir

    var app_okf = Python.import_module("app.okf_loader")
    var count_obj = app_okf.ingest_okf_directory(target_dir, custom_db_path)
    return Int(String(count_obj))
