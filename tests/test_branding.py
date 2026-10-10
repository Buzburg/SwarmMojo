"""Public commands and packaged launchers share the new brand and existing state."""

import importlib
import json
from pathlib import Path
import subprocess
import sys
import tomllib
import unittest

import aeon
import swarm_mojo

from scripts.package import source_files


ROOT = Path(__file__).resolve().parents[1]


class BrandingTests(unittest.TestCase):
    def test_public_and_legacy_module_commands_report_the_package_version(self) -> None:
        project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']
        self.assertEqual(project['name'], 'swarm-mojo')
        self.assertEqual(project['version'], swarm_mojo.__version__)
        self.assertEqual(swarm_mojo.__version__, aeon.__version__)
        for module in ('swarm_mojo', 'aeon'):
            with self.subTest(module=module):
                result = subprocess.run([sys.executable, '-m', module, '--version'], cwd=ROOT,
                                        capture_output=True, text=True, timeout=15, check=True)
                self.assertEqual(result.stdout.strip(), project['version'])

    def test_console_aliases_call_the_same_implementation(self) -> None:
        scripts = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']['scripts']
        implementations = []
        for command in ('swarm-mojo', 'aeon'):
            module, function = scripts[command].split(':')
            implementations.append(getattr(importlib.import_module(module), function))
        self.assertIs(implementations[0], implementations[1])

    def test_release_includes_new_entry_points_and_matching_desktop_assets(self) -> None:
        selected = {path.relative_to(ROOT).as_posix() for path in source_files(ROOT)}
        expected = {'swarm_mojo/__init__.py', 'swarm_mojo/__main__.py', 'packaging/swarm-mojo-menu',
                    'packaging/swarm-mojo.desktop', 'packaging/swarm-mojo-sglang@.service',
                    'packaging/omarchy/io.local.swarm-mojo/manifest.json',
                    'packaging/omarchy/io.local.swarm-mojo/BarWidget.qml'}
        self.assertTrue(expected <= selected)
        manifest = json.loads((ROOT / 'packaging/omarchy/io.local.swarm-mojo/manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['id'], 'io.local.swarm-mojo')
        self.assertEqual(manifest['version'], swarm_mojo.__version__)
        self.assertTrue((ROOT / 'packaging/omarchy' / manifest['id'] / manifest['entryPoints']['barWidget']).is_file())
        desktop = (ROOT / 'packaging/swarm-mojo.desktop').read_text(encoding='utf-8')
        self.assertIn('Exec=swarm-mojo-menu\n', desktop)
        self.assertIn('Name=Swarm Mojo\n', desktop)


if __name__ == '__main__':
    unittest.main()
