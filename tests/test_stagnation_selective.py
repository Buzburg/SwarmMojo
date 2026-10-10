import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from aeon.choice_eval import selective_metrics
from aeon.config import load
from aeon.engine import Harness
from aeon.memory import Memory
from aeon.recovery import repeated_failure


def event(index, ok=False, error='permission denied', tool='read_file'):
    return {'kind': 'tool', 'event_id': index,
            'action': {'tool': tool, 'args': {'path': str(index)}},
            'result': {'ok': ok, 'error': error}}


class StagnationTests(unittest.TestCase):
    def test_changed_arguments_same_failure(self):
        self.assertEqual(repeated_failure([event(i) for i in range(3)])['observed_event_ids'], [0, 1, 2])

    def test_success_changed_error_or_tool_resets(self):
        for last in (event(3, ok=True), event(3, error='different'), event(3, tool='search')):
            self.assertIsNone(repeated_failure([event(1), event(2), last]))
        self.assertIsNone(repeated_failure([event(i, error='') for i in range(3)]))

    def test_control_events_do_not_reset(self):
        self.assertIsNotNone(repeated_failure([event(1), {'kind': 'model'}, event(2), event(3)]))

    def test_engine_stops_before_fourth_call_and_on_resume(self):
        class Model:
            calls = 0
            def decide(self, *args):
                self.calls += 1
                return {'actions': [{'tool': 'read_file', 'args': {'path': str(self.calls)}}], 'answer': '', 'done': False}, {}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); memory = Memory(root/'state'); model = Model()
            try:
                harness = Harness(load(), memory, root, backend=model)
                with patch.object(harness.tools, 'prepare', side_effect=ValueError('permission denied')):
                    result = harness.run('Investigate missing inputs')
                self.assertEqual(result['status'], 'blocked')
                self.assertEqual(model.calls, 3)
                self.assertTrue(any(e['kind'] == 'stuck' for e in memory.events(result['session'])))
                harness.run(sid=result['session'])
                self.assertEqual(model.calls, 3)
            finally:
                memory.close()


def answer(choice='0', probability=.95, margin=.9):
    return {'choice': choice, 'probabilities': {choice: probability}, 'margin': margin}


class SelectiveTests(unittest.TestCase):
    def test_accuracy_coverage_and_wrong_acceptance(self):
        rows = [{'label': label, 'forward': answer(), 'reversed': answer()} for label in (0, 1)]
        rows.append({'label': 0, 'forward': answer(), 'reversed': answer('1')})
        report = selective_metrics(rows)[-1]
        self.assertEqual(report['accepted'], 2)
        self.assertEqual(report['wrong_accepted'], 1)
        self.assertEqual(report['accuracy_when_accepted'], .5)
        self.assertAlmostEqual(report['coverage'], 2/3)

    def test_reverse_confidence_and_margin_gate(self):
        for reverse in (answer(probability=.6), answer(margin=.1)):
            report = selective_metrics([{'label': 0, 'forward': answer(), 'reversed': reverse}])[-1]
            self.assertEqual(report['accepted'], 0)
            self.assertIsNone(report['accuracy_when_accepted'])

    def test_empty_is_not_perfect_accuracy(self):
        self.assertIsNone(selective_metrics([])[0]['accuracy_when_accepted'])


if __name__ == '__main__':
    unittest.main()
