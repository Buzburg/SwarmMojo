"""Live installed-CLI check with real embeddings and disposable local sources."""
import json
from pathlib import Path
import subprocess
import tempfile

from app.db import get_connection
from app.rag_engine import hybrid_search


def goose(*args: str) -> dict:
    result = subprocess.run(['/usr/local/bin/goose', *args], capture_output=True,
                            text=True, check=True, timeout=120)
    return json.loads(result.stdout)


def main() -> None:
    sources: list[str] = []
    connection = get_connection()
    with tempfile.TemporaryDirectory(prefix='omarchy-intake-check-') as temporary:
        base = Path(temporary)
        try:
            for name in ('alpha', 'beta'):
                repo = base / name
                repo.mkdir()
                subprocess.run(['git', 'init', '-q', str(repo)], check=True)
                (repo / 'README.md').write_text(
                    f'The intake verification {name} repository stores violet lantern calibration records.\n')
                subprocess.run(['git', '-C', str(repo), 'add', 'README.md'], check=True)
                preview = goose('--add-repo', str(repo), '--preview')
                assert preview['files'] == ['README.md'], preview
                result = goose('--add-repo', str(repo))
                sources.append(result['id'])
                assert result['status'] == 'ready' and result['indexed_files'] == 1, result
            query = 'intake verification violet lantern calibration records'
            results = hybrid_search(query, limit=20)
            for source_id in sources:
                doc_id = f'source:{source_id}/README.md'
                assert any(item['doc_id'] == doc_id for item in results), results
                assert connection.execute('SELECT 1 FROM okf_registry WHERE doc_id=?', (doc_id,)).fetchone()
            (base / 'alpha/README.md').write_text('New user content remains after index removal.\n')
        finally:
            for source_id in sources:
                subprocess.run(['/usr/local/bin/goose', '--remove-source', source_id], check=True, timeout=30)
        assert (base / 'alpha/README.md').read_text().startswith('New user content')
        results = hybrid_search('intake verification violet lantern calibration records', limit=20)
        assert not any(any(item['doc_id'].startswith(f'source:{sid}/') for sid in sources) for item in results)
        for source_id in sources:
            assert not connection.execute('SELECT 1 FROM okf_registry WHERE doc_id LIKE ?',
                                          (f'source:{source_id}/%',)).fetchone()
    print(json.dumps({'installed_cli': 'passed', 'real_embeddings': 'passed',
                      'duplicate_filenames': 'passed', 'cross_process_cache_refresh': 'passed',
                      'removal_preserves_originals': 'passed'}, indent=2))


if __name__ == '__main__':
    main()
