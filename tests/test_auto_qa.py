"""Tests for bounded Auto-QA policy tuning."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from scripts import auto_qa


class PolicyTests(unittest.TestCase):
    def write_policy(self, **overrides):
        policy = {
            "version": 1,
            "minimum_clean_runs": 1,
            "post_failure_clean_runs": 2,
            "maximum_runs": 3,
        }
        policy.update(overrides)
        temporary = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False)
        self.addCleanup(Path(temporary.name).unlink, missing_ok=True)
        with temporary:
            json.dump(policy, temporary)
        return Path(temporary.name)

    def test_loads_policy_within_safety_bounds(self):
        policy = auto_qa.load_policy(self.write_policy())
        self.assertEqual(policy, auto_qa.Policy(1, 2, 3))

    def test_rejects_policy_that_can_skip_tests(self):
        with self.assertRaisesRegex(ValueError, "minimum_clean_runs"):
            auto_qa.load_policy(self.write_policy(minimum_clean_runs=0))

    def test_rejects_unbounded_runs(self):
        with self.assertRaisesRegex(ValueError, "maximum_runs"):
            auto_qa.load_policy(self.write_policy(maximum_runs=5))


class TuningTests(unittest.TestCase):
    def run_outcomes(self, outcomes):
        calls = []

        def runner(command, *, check, cwd):
            calls.append((command, check, cwd))
            return SimpleNamespace(returncode=outcomes[len(calls) - 1])

        policy = auto_qa.Policy(1, 2, 3)
        with contextlib.redirect_stderr(io.StringIO()):
            result = auto_qa.run(policy, runner)
        return result, calls

    def test_clean_suite_stops_at_minimum(self):
        result, calls = self.run_outcomes([0])
        self.assertEqual(result, 0)
        self.assertEqual(len(calls), 1)

    def test_failure_raises_confirmation_threshold_but_remains_fatal(self):
        result, calls = self.run_outcomes([1, 0, 0])
        self.assertEqual(result, 1)
        self.assertEqual(len(calls), 3)

    def test_repeated_failures_stop_at_maximum(self):
        result, calls = self.run_outcomes([1, 1, 1])
        self.assertEqual(result, 1)
        self.assertEqual(len(calls), 3)


if __name__ == "__main__":
    unittest.main()
