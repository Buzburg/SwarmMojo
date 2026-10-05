"""Different source trees must not overwrite same-named documents."""
from app import okf_loader
from app.db import get_connection
from test_ingestion_quality import setup_ingestion


def test_namespaced_files_preserve_both_repositories(tmp_path, monkeypatch):
    database, _, _ = setup_ingestion(tmp_path, monkeypatch)
    for name, contents in [('first', 'Alpha repository uses the violet protocol.'),
                           ('second', 'Beta repository uses the amber protocol.')]:
        folder = tmp_path / name
        folder.mkdir()
        path = folder / 'README.md'
        path.write_text(contents)
        assert okf_loader.ingest_document_file(path, database, doc_id=f'{name}/README.md')
    conn = get_connection(database)
    assert conn.execute('SELECT COUNT(*) FROM okf_registry').fetchone()[0] == 2
    assert conn.execute("SELECT content FROM fts_chunks WHERE doc_id='first/README.md'").fetchone()[0].startswith('Alpha')
    path = tmp_path / 'second/README.md'
    path.write_text('Beta repository now uses the green protocol.')
    assert okf_loader.ingest_document_file(path, database, doc_id='second/README.md')
    assert conn.execute('SELECT COUNT(*) FROM okf_registry').fetchone()[0] == 2
    assert 'violet' in conn.execute("SELECT content FROM fts_chunks WHERE doc_id='first/README.md'").fetchone()[0]
