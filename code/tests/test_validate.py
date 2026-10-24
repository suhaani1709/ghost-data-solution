"""Unit tests for code/evaluation/validate.py.

COMPLETE with steps [] is allowed by problem_statement.md (zero-link rule,
NOTES.md), so it is a warning, not an error. INCOMPLETE with [] stays an error.

Run:  python3 code/tests/test_validate.py
All inputs here are synthetic; no dataset content.
"""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evaluation"))

import validate  # noqa: E402

REQUESTS = pd.DataFrame({"case_id": ["c1", "c2"], "audit_at": ["2026-01-02T00:00:00Z"] * 2})
MANIFEST = pd.DataFrame({"file_id": ["f1"], "captured_at": ["2026-01-01T00:00:00Z"]})
STEP = ('[{"step_no":1,"phase":"VERIFICATION","system_id":"account_service",'
        '"resource_id":"account_1","operation":"VERIFY_RECORD_ABSENT","state":"ABSENT",'
        '"evidence_id":"f1"}]')


def run(rows):
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "out.csv"
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["case_id", "deletion_status", "steps_json"])
            w.writerows(rows)
        return validate.validate(path, REQUESTS, MANIFEST, set(), {})


class ValidateTest(unittest.TestCase):
    def test_complete_with_no_steps_is_a_warning(self):
        n, errors, _, bad, warnings = run([("c1", "COMPLETE", "[]"), ("c2", "COMPLETE", STEP)])
        self.assertEqual((n, sum(errors.values()), bad), (2, 0, set()))
        self.assertEqual(dict(warnings), {"COMPLETE with no steps": 1})

    def test_incomplete_with_no_steps_is_an_error(self):
        _, errors, _, bad, warnings = run([("c1", "INCOMPLETE", "[]"), ("c2", "COMPLETE", STEP)])
        self.assertEqual(dict(errors), {"INCOMPLETE with no steps": 1})
        self.assertEqual((bad, sum(warnings.values())), ({"c1"}, 0))

    def test_not_applicable_with_no_steps_is_not_warned(self):
        _, errors, _, _, warnings = run([("c1", "NOT_APPLICABLE", "[]"), ("c2", "COMPLETE", "[]")])
        self.assertFalse(errors)
        self.assertEqual(sum(warnings.values()), 1)


if __name__ == "__main__":
    unittest.main(verbosity=1)
