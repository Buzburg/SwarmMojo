"""Offline ingestion performance and atomicity tests; no real model is loaded."""
import re
import sqlite3

import numpy as np
import pytest

from app import okf_loader, topic
from app.config import EMBEDDING_DIM
from app.db import get_connection as create_connection, init_database


class FakeEmbeddingModel:
    def __init__(self, values=None):
        self.values = values
        self.calls = []

    def encode(self, chunks, *, output_value, batch_size):
        self.calls.append((list(chunks), output_value, batch_size))
        if isinstance(self.values, Exception):
            raise self.values
        if self.values is not None:
            return self.values
        return np.ones((len(chunks), EMBEDDING_DIM), dtype=np.float32)


def setup_ingestion(tmp_path, monkeypatch, model=None):
    database = tmp_path / 'ingestion.db'
    init_database(database)
    model = model or FakeEmbeddingModel()
    statements = []
    active_connection = []

    def shared_connection(db_path=None, **kwargs):
        if active_connection and kwargs.get('reuse', True):
            try:
                active_connection[0].execute('SELECT 1')
                return active_connection[0]
            except sqlite3.ProgrammingError:
                active_connection.clear()
        connection = create_connection(database, reuse=False)
        connection.set_trace_callback(statements.append)
        active_connection.append(connection)
        return connection

    monkeypatch.setattr(okf_loader, 'get_connection', shared_connection)
    monkeypatch.setattr(topic, 'get_connection', shared_connection)
    monkeypatch.setattr(okf_loader, 'get_embedding_model', lambda: model)
    return database, model, statements


def read_index(database):
    return create_connection(database, reuse=False)


def write_paragraphs(path, *paragraphs):
    path.write_text('\n\n'.join(paragraphs), encoding='utf-8')


def test_document_ingestion_batches_topic_writes_into_one_commit(tmp_path, monkeypatch):
    database, model, statements = setup_ingestion(tmp_path, monkeypatch)
    document = tmp_path / 'guide.md'
    write_paragraphs(document,
                     'Alpha policy renewal applies to accounts.',
                     'Beta warranty coverage protects equipment.',
                     'Gamma storage guidance preserves inventory.')

    assert okf_loader.ingest_document_file(document, database)

    savepoint_releases = [sql for sql in statements if re.fullmatch(r'\s*RELEASE SAVEPOINT roms_ingest_document\s*', sql, re.I)]
    commits = [sql for sql in statements if re.fullmatch(r'\s*COMMIT\s*', sql, re.I)]
    topic_count_updates = [sql for sql in statements if re.search(r'UPDATE topics SET chunk_count', sql, re.I)]
    assert len(savepoint_releases) + len(commits) == 1
    assert len(topic_count_updates) == 1
    assert len(model.calls) == 1
    assert len(model.calls[0][0]) == 3
    connection = read_index(database)
    assert connection.execute('SELECT count(*) FROM fts_chunks').fetchone()[0] == 3
    assert connection.execute('SELECT count(*) FROM vec_chunks').fetchone()[0] == 3
    assert connection.execute('SELECT count(*) FROM chunk_topics').fetchone()[0] > 0
    assert all(count == actual for count, actual in connection.execute(
        'SELECT t.chunk_count, count(ct.chunk_id) FROM topics t '
        'LEFT JOIN chunk_topics ct USING(topic_id) GROUP BY t.topic_id'))
    connection.close()


def test_failed_embedding_preserves_previously_indexed_document(tmp_path, monkeypatch):
    database, model, _ = setup_ingestion(tmp_path, monkeypatch)
    document = tmp_path / 'guide.md'
    write_paragraphs(document, 'Approved original procedure with alpha detail.')
    assert okf_loader.ingest_document_file(document, database)
    connection = read_index(database)
    old_checksum = connection.execute('SELECT checksum FROM okf_registry WHERE doc_id = ?',
                                      (document.name,)).fetchone()[0]
    old_chunks = connection.execute('SELECT chunk_id, content FROM fts_chunks ORDER BY chunk_id').fetchall()
    old_vectors = connection.execute('SELECT chunk_id FROM vec_chunks ORDER BY chunk_id').fetchall()
    connection.close()

    write_paragraphs(document, 'Replacement procedure contains beta detail.')
    model.values = RuntimeError('simulated model failure')
    with pytest.raises(RuntimeError, match='simulated model failure'):
        okf_loader.ingest_document_file(document, database)

    connection = read_index(database)
    assert connection.execute('SELECT checksum FROM okf_registry WHERE doc_id = ?',
                              (document.name,)).fetchone()[0] == old_checksum
    assert connection.execute('SELECT chunk_id, content FROM fts_chunks ORDER BY chunk_id').fetchall() == old_chunks
    assert connection.execute('SELECT chunk_id FROM vec_chunks ORDER BY chunk_id').fetchall() == old_vectors
    connection.close()


def test_index_write_failure_rolls_back_all_replacement_rows(tmp_path, monkeypatch):
    database, _, _ = setup_ingestion(tmp_path, monkeypatch)
    document = tmp_path / 'guide.md'
    write_paragraphs(document, 'Approved original procedure with alpha detail.')
    assert okf_loader.ingest_document_file(document, database)
    connection = read_index(database)
    old_checksum = connection.execute('SELECT checksum FROM okf_registry WHERE doc_id = ?',
                                      (document.name,)).fetchone()[0]
    old_chunks = connection.execute('SELECT chunk_id, content FROM fts_chunks ORDER BY chunk_id').fetchall()
    connection.close()
    original_batch_tag = topic.tag_chunks_with_topics

    def fail_after_batch_topic_write(chunks, conn, doc_type='general', refresh_topic_ids=None):
        original_batch_tag(chunks, conn, doc_type=doc_type, refresh_topic_ids=refresh_topic_ids)
        raise RuntimeError('simulated index write failure')

    monkeypatch.setattr(topic, 'tag_chunks_with_topics', fail_after_batch_topic_write)
    write_paragraphs(document, 'Replacement procedure contains beta detail.')
    with pytest.raises(RuntimeError, match='simulated index write failure'):
        okf_loader.ingest_document_file(document, database)

    connection = read_index(database)
    assert connection.execute('SELECT checksum FROM okf_registry WHERE doc_id = ?',
                              (document.name,)).fetchone()[0] == old_checksum
    assert connection.execute('SELECT chunk_id, content FROM fts_chunks ORDER BY chunk_id').fetchall() == old_chunks
    connection.close()


@pytest.mark.parametrize('bad', [
    np.ones((1, EMBEDDING_DIM), dtype=np.float32),
    np.full((2, EMBEDDING_DIM), np.nan, dtype=np.float32),
], ids=['wrong-row-count', 'non-finite'])
def test_invalid_batch_embeddings_do_not_replace_existing_document(tmp_path, monkeypatch, bad):
    database, _, _ = setup_ingestion(tmp_path, monkeypatch)
    document = tmp_path / 'guide.md'
    write_paragraphs(document, 'Approved original procedure with alpha detail.')
    assert okf_loader.ingest_document_file(document, database)
    connection = read_index(database)
    old_checksum = connection.execute('SELECT checksum FROM okf_registry WHERE doc_id = ?',
                                      (document.name,)).fetchone()[0]
    connection.close()

    write_paragraphs(document,
                     'Replacement procedure contains beta detail.',
                     'Second replacement chunk contains gamma detail.')
    monkeypatch.setattr(okf_loader, 'get_embedding_model', lambda: FakeEmbeddingModel(bad))
    with pytest.raises(ValueError, match='embedding'):
        okf_loader.ingest_document_file(document, database)

    connection = read_index(database)
    assert connection.execute('SELECT checksum FROM okf_registry WHERE doc_id = ?',
                              (document.name,)).fetchone()[0] == old_checksum
    assert connection.execute('SELECT count(*) FROM fts_chunks WHERE doc_id = ?',
                              (document.name,)).fetchone()[0] == 1
    connection.close()


def test_changed_document_recomputes_old_topic_counts(tmp_path, monkeypatch):
    database, _, _ = setup_ingestion(tmp_path, monkeypatch)
    document = tmp_path / 'guide.md'
    write_paragraphs(document, 'Zyglorian policy guides alpha equipment.')
    assert okf_loader.ingest_document_file(document, database)
    connection = read_index(database)
    assert connection.execute("SELECT chunk_count FROM topics WHERE topic_id = 'zyglorian'").fetchone()[0] == 1
    connection.close()

    write_paragraphs(document, 'Quorvex warranty guides beta equipment.')
    assert okf_loader.ingest_document_file(document, database)

    connection = read_index(database)
    assert connection.execute("SELECT chunk_count FROM topics WHERE topic_id = 'zyglorian'").fetchone()[0] == 0
    assert connection.execute("SELECT chunk_count FROM topics WHERE topic_id = 'quorvex'").fetchone()[0] == 1
    connection.close()
