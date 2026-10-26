from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import measure


def sample(identifier, group='before', success=True, tokens=100):
    return dict(task_id=identifier, family='synthetic-test', model='synthetic-model', effort='xhigh', basis='synthetic-counts', source='unit-test-only', group=group, success=success, input_tokens=tokens, cached_tokens=20, output_tokens=10, tool_calls=None, retries=None, elapsed_seconds=None)


class MeasurementTests(unittest.TestCase):
    def test_unknown_metrics_not_zero(self):
        row = sample('one')
        row['input_tokens'] = None
        self.assertIsNone(measure.aggregate([row])['total_tokens'])
        self.assertIsNone(measure.aggregate([row])['tokens_per_success'])

    def test_cached_not_added_twice(self):
        self.assertEqual(measure.aggregate([sample('one')])['total_tokens'], 110)

    def test_cached_cannot_exceed_input(self):
        row = sample('one')
        row['cached_tokens'] = 101
        with self.assertRaises(ValueError):
            measure.validate(row)

    def test_failures_in_success_cost(self):
        rows = [sample('one', success=False), sample('two')]
        result = measure.aggregate(rows)
        self.assertEqual(result['tokens_per_success'], 220)

    def test_no_success_no_division(self):
        self.assertIsNone(measure.aggregate([sample('one', success=False)])['tokens_per_success'])

    def test_small_sample_no_percentage(self):
        result = measure.report([sample('one'), sample('one', group='after')])[0]
        self.assertFalse(result['minimum_sample_size_met'])
        self.assertIsNone(result['tokens_per_success_reduction_percent'])

    def test_manually_duplicated_samples_refused(self):
        with self.assertRaises(ValueError):
            measure.report([sample('same'), sample('same')])

    def test_different_models_separate(self):
        a = sample('one')
        b = sample('two', group='after')
        b['model'] = 'different-synthetic-model'
        self.assertEqual(len(measure.report([a, b])), 2)

    def test_complete_same_cohort_comparison(self):
        rows = [sample(str(i)) for i in range(3)] + [sample(str(i), group='after', tokens=45) for i in range(3)]
        result = measure.report(rows)[0]
        self.assertAlmostEqual(result['tokens_per_success_reduction_percent'], 50)

    def test_quality_decline_no_savings_claim(self):
        rows = [sample(str(i)) for i in range(3)] + [sample(str(i), group='after', success=i != 0, tokens=45) for i in range(3)]
        self.assertIsNone(measure.report(rows)[0]['tokens_per_success_reduction_percent'])

    def test_negative_and_nonfinite_refused(self):
        for key, value in [('input_tokens', -1), ('elapsed_seconds', float('nan'))]:
            row = sample('one')
            row[key] = value
            with self.assertRaises(ValueError):
                measure.validate(row)

    def test_duplicate_record_not_double_counted(self):
        parent = ROOT / '.test-work'
        parent.mkdir(exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=parent)
        base = Path(temp.name)
        try:
            path = base / 'measurements.jsonl'
            measure.record(path, sample('one'))
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                measure.record(path, sample('one'))
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(len(measure.read_samples(path)), 1)
        finally:
            self.assertTrue(base.resolve().is_relative_to(parent.resolve()))
            temp.cleanup()


if __name__ == '__main__':
    unittest.main()
