"""Ownership links from evidence captured after audit_at (identity is a static fact);
state and citations still come only from evidence <= audit_at.

- Linker.link(..., any_time=True) indexes identifier matches from every file; reference
  following stays <= audit_at.
- planner.build_steps_unproven: a retained record with no state <= audit_at is PRESENT
  with evidence "" (a future check). It is kept when the case is INCOMPLETE (its
  verification step has evidence "" anyway) and dropped when the case would be COMPLETE
  (a COMPLETE verification must cite evidence <= audit_at).

Run:  python3 code/tests/test_link_after_audit.py
All inputs here are synthetic; no dataset content.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghost import linking, planner  # noqa: E402
from test_linking_state import IDENT, frame, ids, obs  # noqa: E402

AUDIT = "2026-02-01T00:00:00Z"
TREAT = planner.load_treatments()


class LinkAnyTimeTest(unittest.TestCase):
    def test_later_file_links_only_with_any_time(self):
        df = frame(obs("f9", "2026-03-01T00:00:00Z", "security_service", "audit_record_1", "PRESENT",
                       identifiers=ids(user_ids=["user_7"])))
        self.assertEqual(linking.Linker(df).link(IDENT, AUDIT), {})
        self.assertEqual(list(linking.Linker(df).link(IDENT, AUDIT, any_time=True)),
                         [("security_service", "audit_record_1")])


class UnprovenRetainedTest(unittest.TestCase):
    AUDIT_REC = ("security_service", "audit_record_1", "SECURITY_AUDIT_LOG", "PRESENT", "")
    LEFT = ("search_service", "search_1", "SEARCH_INDEX_ENTRY", "PRESENT", "f1")
    GONE = ("account_service", "account_1", "USER_PROFILE", "ABSENT", "f2")

    def test_kept_in_incomplete_case(self):
        status, steps = planner.build_steps_unproven([self.AUDIT_REC, self.LEFT], TREAT)
        self.assertEqual(status, "INCOMPLETE")
        self.assertIn(("VERIFY_RECORD_PRESENT", "audit_record_1", ""),
                      [(s["operation"], s["resource_id"], s["evidence_id"]) for s in steps])

    def test_dropped_from_complete_case(self):
        status, steps = planner.build_steps_unproven([self.AUDIT_REC, self.GONE], TREAT)
        self.assertEqual((status, [s["resource_id"] for s in steps]), ("COMPLETE", ["account_1"]))

    def test_only_unproven_resources_give_complete_empty(self):
        self.assertEqual(planner.build_steps_unproven([self.AUDIT_REC], TREAT), ("COMPLETE", []))



class CategoryAnyTimeTest(unittest.TestCase):
    def test_hint_from_a_later_file_when_none_before_audit(self):
        from ghost import state
        df = frame(obs("f9", "2026-03-01T00:00:00Z", "support_platform", "support_1", "PRESENT",
                       category="SUPPORT_ATTACHMENT"))
        self.assertEqual(state.StateResolver(df).category("support_platform", "support_1", AUDIT),
                         "SUPPORT_MESSAGE")                      # system fallback
        self.assertEqual(state.StateResolver(df, category_any_time=True).category(
            "support_platform", "support_1", AUDIT), "SUPPORT_ATTACHMENT")

    def test_hint_before_audit_still_wins(self):
        from ghost import state
        df = frame(obs("f1", "2026-01-01T00:00:00Z", "support_platform", "support_1", "PRESENT",
                       category="SUPPORT_MESSAGE"),
                   obs("f9", "2026-03-01T00:00:00Z", "support_platform", "support_1", "PRESENT",
                       category="SUPPORT_ATTACHMENT"))
        self.assertEqual(state.StateResolver(df, category_any_time=True).category(
            "support_platform", "support_1", AUDIT), "SUPPORT_MESSAGE")


if __name__ == "__main__":
    unittest.main(verbosity=1)
