"""Unit tests for the zero-link rule (NOTES.md, "Zero-link rule").

A deletion-authorized request whose linking yields no resource at audit_at
is COMPLETE with steps []: no evidence shows a remaining copy (an INCOMPLETE
finding must cite evidence), and no verification step is invented without
evidence. Non-deletion requests stay NOT_APPLICABLE with [].

Run:  python3 code/tests/test_zero_link.py
All inputs here are synthetic; no dataset content.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghost import planner  # noqa: E402

TREATMENTS = {"USER_PROFILE": planner.TREATMENT_BY_ACTION["DELETE"]}


class ZeroLinkTest(unittest.TestCase):
    def test_no_resources_is_complete_with_no_steps(self):
        self.assertEqual(planner.build_steps([], TREATMENTS), ("COMPLETE", []))

    def test_zero_link_flag(self):
        self.assertTrue(planner.is_zero_link([]))
        self.assertFalse(planner.is_zero_link(
            [("account_service", "account_1", "USER_PROFILE", "ABSENT", "f1")]))

    def test_one_resource_still_needs_its_evidence_step(self):
        status, steps = planner.build_steps(
            [("account_service", "account_1", "USER_PROFILE", "ABSENT", "f1")], TREATMENTS)
        self.assertEqual((status, [s["evidence_id"] for s in steps]), ("COMPLETE", ["f1"]))


if __name__ == "__main__":
    unittest.main(verbosity=1)
