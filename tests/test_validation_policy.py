import pytest

from app.validation_policy import command_for


@pytest.mark.parametrize('payload', [
    {'command': 'shell', 'files': ['file.py']},
    {'command': 'python.syntax', 'files': ['../file.py']},
    {'command': 'python.syntax', 'files': ['/tmp/file.py']},
    {'command': 'python.syntax', 'files': ['-option.py']},
    {'command': 'python.syntax', 'files': ['file.py'], 'image': 'attacker'},
    {'command': 'python.syntax', 'files': 'file.py'},
    {'command': 'python.syntax', 'files': []},
    {'command': 'python.tests', 'args': ['-c', 'anything']},
    {'command': 'python.tests', 'network': 'host'},
])
def test_arbitrary_commands_and_options_rejected(tmp_path, payload):
    (tmp_path / 'file.py').write_text('x = 1')
    with pytest.raises(ValueError):
        command_for(payload, tmp_path)


def test_symlink_input_rejected(tmp_path):
    original = tmp_path / 'original.py'
    original.write_text('x = 1')
    (tmp_path / 'link.py').symlink_to(original)
    with pytest.raises(ValueError, match='Symlinks'):
        command_for({'command': 'python.syntax', 'files': ['link.py']}, tmp_path)


def test_registered_command_has_fixed_executable_and_flags(tmp_path):
    (tmp_path / 'file.py').write_text('x = 1')
    assert command_for({'command': 'python.syntax', 'files': ['file.py']}, tmp_path) == [
        '/usr/bin/python3', '-I', '-B', '-m', 'py_compile', '--', 'file.py']
