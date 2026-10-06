"""Run the declared repository-integration checks and write machine-readable evidence."""
import argparse
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=ROOT / 'build/workbench-tests.json')
    parser.add_argument('--check-report', type=Path)
    parser.add_argument('--native', action='store_true')
    parser.add_argument('--model', type=Path)
    args = parser.parse_args()
    if args.check_report:
        report = json.loads(args.check_report.read_text())
        if report.get('success') is not True or report.get('tests', 0) < 27:
            raise SystemExit('Workbench verification did not pass the declared checks')
        return
    args.report.parent.mkdir(parents=True, exist_ok=True)
    junit = args.report.with_suffix('.xml')
    env = dict(os.environ)
    env.pop('OMARCHY_STATE_LIBRARY', None)
    env.pop('OMARCHY_STATE_MODEL', None)
    if args.native:
        if args.model is None or not (ROOT / 'build/libomarchy_state.so').is_file():
            raise SystemExit('Native verification requires the built adapter and --model')
        env.update(OMARCHY_STATE_LIBRARY=str(ROOT / 'build/libomarchy_state.so'),
                   OMARCHY_STATE_MODEL=str(args.model.resolve()))
    suites = ['context', 'receipts', 'integrations', 'triggertangle', 'baseline', 'state', 'package']
    started = time.monotonic()
    command = [sys.executable, '-m', 'pytest', *['tests/test_workbench_' + name + '.py' for name in suites],
               '-q', '--tb=short', '--show-capture=no', '--junitxml=' + str(junit.resolve())]
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=240, check=False)
    log = args.report.with_suffix('.log')
    log.write_text(result.stdout + result.stderr)
    cases = list(ET.parse(junit).iter('testcase')) if junit.exists() else []
    skipped = sum(case.find('skipped') is not None for case in cases)
    report = {'success': result.returncode == 0 and len(cases) >= 27 and skipped == (0 if args.native else 1),
        'tests': len(cases), 'skipped': skipped, 'seconds': time.monotonic() - started,
        'native_state_verified': args.native and result.returncode == 0 and skipped == 0,
        'target_hardware_qualified': False, 'log': str(log.resolve())}
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    raise SystemExit(0 if report['success'] else 1)


if __name__ == '__main__':
    main()
