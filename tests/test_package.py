from pathlib import Path
import os
import stat
import tempfile
import unittest
from unittest.mock import patch

from scripts.package import DIRECTORIES, EXTRA_FILES, ROOT_FILES, source_files


class PackageSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix='swarm-mojo-package-selection-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in DIRECTORIES:
            (self.root / name).mkdir()
        for name in (*ROOT_FILES, *EXTRA_FILES):
            self.add_file(name)

    def add_file(self, name: str) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('release fixture', encoding='utf-8')
        return path

    def test_source_and_license_assets_are_complete_without_building_a_wheel(self) -> None:
        expected = set(ROOT_FILES) | EXTRA_FILES | {
            'aeon/rehearsal.py', 'aeon/defaults.toml', 'aeon/assistant.html', 'tests/test_rehearsal.py',
            'swarm_mojo/__init__.py', 'swarm_mojo/__main__.py',
            'docs/REHEARSAL.md', 'scripts/verify_package.py', 'scripts/install-omarchy.sh', 'scripts/check_review_ui.cjs',
            'examples/triggertangle/contact-suite.json', '.github/workflows/tests.yml',
            'packaging/omarchy/io.local.swarm-mojo/manifest.json', 'packaging/swarm-mojo.desktop',
        }
        for name in expected:
            self.add_file(name)
        selected = {path.relative_to(self.root).as_posix() for path in source_files(self.root)}
        self.assertEqual(selected, expected)

    def test_private_state_and_unrecognized_binary_types_are_excluded_at_any_depth(self) -> None:
        excluded = [
            'docs/.env', 'examples/deep/.env.production', 'aeon/.aeon/history.json',
            'scripts/__pycache__/saved.py', 'examples/credentials.json', 'docs/credentials-backup.json',
            'docs/secrets/private.md', 'examples/.state/snapshot.json', 'aeon/vendor/weights/model.json',
            'examples/model.gguf', 'aeon/model.pt', 'docs/model.safetensors', 'examples/state.sqlite',
            'scripts/private_key.pem', 'docs/.git/config',
        ]
        for name in excluded:
            self.add_file(name)
        selected = {path.relative_to(self.root).as_posix() for path in source_files(self.root)}
        self.assertTrue(selected.isdisjoint(excluded))
        self.assertEqual(selected, set(ROOT_FILES) | EXTRA_FILES)

    def test_missing_bundled_license_or_runner_fails(self) -> None:
        (self.root / 'aeon/vendor/triggertangle/LICENSE').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing release assets'):
            source_files(self.root)

    def test_links_are_rejected_without_following_the_target(self) -> None:
        link = self.root / 'docs/linked.md'
        try:
            link.symlink_to(self.root / 'README.md')
        except (OSError, NotImplementedError):
            self.skipTest('Symlink creation is unavailable on this host')
        with self.assertRaisesRegex(ValueError, 'links or reparse'):
            source_files(self.root)

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'Named pipes require POSIX')
    def test_nonregular_file_is_rejected_without_reading(self) -> None:
        os.mkfifo(self.root / 'docs/pipe.md')
        with self.assertRaisesRegex(ValueError, 'regular files'):
            source_files(self.root)

    def test_windows_reparse_attributes_are_rejected(self) -> None:
        path = self.add_file('docs/reparse.md')
        original = Path.lstat

        class Reparse:
            st_mode = stat.S_IFREG | 0o600
            st_file_attributes = 0x400

        def info(candidate: Path):
            return Reparse() if candidate == path else original(candidate)

        with patch.object(Path, 'lstat', info), self.assertRaisesRegex(ValueError, 'links or reparse'):
            source_files(self.root)


if __name__ == '__main__':
    unittest.main()
