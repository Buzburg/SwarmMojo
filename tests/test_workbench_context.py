
import pytest
from app.workbench.context import CodeIndex, compact_log


def test_error_heavy_and_unicode_logs_obey_both_budgets():
    raw = '\n'.join(f'error {i}: ' + '界' * 100 for i in range(200))
    result = compact_log(raw, max_lines=12, max_bytes=700)
    assert len(result['text'].splitlines()) <= 12
    assert len(result['text'].encode()) <= 700
    assert result['truncated'] and result['original_lines'] == 200
    assert 'error 0' in result['text']
    assert result['raw_sha256']


def test_index_refreshes_and_python_strings_are_not_callers(tmp_path):
    source = tmp_path / 'module.py'
    source.write_text('def hello():\n    return 1\n\ndef caller():\n    hello()\n    x = "hello()"\n# hello()\n')
    index = CodeIndex(tmp_path)
    found = index.query('hello')
    assert len(found['definitions']) == 1
    assert len(found['callers']) == 1 and found['callers'][0]['line'] == 5
    source.write_text('def renamed():\n    pass\n')
    assert not index.query('hello')['definitions']
    assert index.query('renamed')['definitions']


def test_index_excludes_sensitive_files_and_symlinks(tmp_path):
    (tmp_path / '.env.py').write_text('def secret(): pass\n')
    outside = tmp_path.parent / (tmp_path.name + '-outside.py')
    outside.write_text('def outside(): pass\n')
    (tmp_path / 'escape.py').symlink_to(outside)
    result = CodeIndex(tmp_path).query('outside')
    assert not result['definitions']
    assert not CodeIndex(tmp_path).query('secret')['definitions']
    with pytest.raises(ValueError):
        CodeIndex(tmp_path).query('../escape')


def test_index_reports_bounded_coverage_and_malformed_python(tmp_path):
    for name in ['a.py', 'b.py', 'c.py']:
        (tmp_path / name).write_text('def hello(): pass\n')
    result = CodeIndex(tmp_path, max_files=2).query('hello')
    assert result['truncated'] and result['indexed_files'] == 2
    (tmp_path / 'a.py').write_text('def broken(:')
    assert any(item['path'] == 'a.py' for item in CodeIndex(tmp_path).query('hello')['skipped'])


@pytest.mark.parametrize('lines,size', [(0, 100), (2, 0), (True, 100)])
def test_invalid_log_budgets_rejected(lines, size):
    with pytest.raises(ValueError):
        compact_log('error', max_lines=lines, max_bytes=size)
