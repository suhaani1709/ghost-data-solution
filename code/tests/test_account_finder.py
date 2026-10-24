"""Unit tests for account_finder.py: one account record per deletion case.

Used only when linking found no account_service resource. Candidates are
account_service DELETE_RECORD activity rows in the window around reported_at
(<= audit_at). Accounts that evidence (<= audit_at, not a mere REFERENCED
mention) ties to an identifier other than the subject's are removed. The
user-number pattern only breaks ties among survivors; still ambiguous -> None.

Run:  python3 code/tests/test_account_finder.py
All inputs here are synthetic; no dataset content.
"""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghost import account_finder, loaders  # noqa: E402
from test_linking_state import IDENT, frame, ids, obs  # noqa: E402  (IDENT is user_7)

REPORTED, AUDIT = "2026-05-01T12:00:00Z", "2026-05-10T00:00:00Z"


def act(aid, t, rid, event="DELETE_RECORD", target="account_service"):
    return {"activity_id": aid, "event_time": t, "event_type": event, "source_system": "deletion_worker",
            "target_system": target, "resource_id": rid, "reported_result": "SUCCESS", "details": ""}


def activity(*rows):
    return pd.DataFrame(list(rows), columns=loaders.ACTIVITY_COLUMNS)


def find(activity_rows, obs_rows=()):
    f = account_finder.AccountFinder(frame(*obs_rows), activity(*activity_rows))
    return f.find(IDENT, REPORTED, AUDIT)


class AccountFinderTest(unittest.TestCase):
    def test_single_candidate_in_window(self):
        self.assertEqual(find([act("a1", "2026-05-01T11:20:00Z", "account_40")]), ("account_40", "a1"))

    def test_window_bounds(self):
        self.assertIsNone(find([act("a1", "2026-05-01T10:00:00Z", "account_40")]))   # 120 min before
        self.assertIsNone(find([act("a1", "2026-05-01T12:30:00Z", "account_40")]))   # 30 min after
        self.assertEqual(find([act("a1", "2026-05-01T12:05:00Z", "account_40")]), ("account_40", "a1"))

    def test_other_systems_and_operations_ignored(self):
        self.assertIsNone(find([act("a1", "2026-05-01T11:50:00Z", "search_40", target="search_service"),
                                act("a2", "2026-05-01T11:50:00Z", "account_41", event="UPDATE_RECORD")]))

    def test_account_tied_to_another_user_is_removed(self):
        rows = [act("a1", "2026-05-01T11:20:00Z", "account_40"), act("a2", "2026-05-01T11:30:00Z", "account_41")]
        other = obs("f1", "2026-04-01T00:00:00Z", "account_service", "account_41", "PRESENT",
                    identifiers=ids(user_ids=["user_99"]))
        self.assertEqual(find(rows, [other]), ("account_40", "a1"))

    def test_ties_after_audit_or_from_referenced_mentions_do_not_remove(self):
        rows = [act("a1", "2026-05-01T11:20:00Z", "account_40"), act("a2", "2026-05-01T11:30:00Z", "account_41")]
        late = obs("f1", "2026-06-01T00:00:00Z", "account_service", "account_41", "PRESENT",
                   identifiers=ids(user_ids=["user_99"]))
        mention = obs("f2", "2026-04-01T00:00:00Z", "account_service", "account_41", "REFERENCED",
                      identifiers=ids(user_ids=["user_99"]))
        self.assertIsNone(find(rows, [late, mention]))     # two survivors, no number match -> ambiguous

    def test_user_number_breaks_ties_only_among_survivors(self):
        rows = [act("a1", "2026-05-01T11:20:00Z", "account_40"), act("a2", "2026-05-01T11:30:00Z", "account_007")]
        self.assertEqual(find(rows), ("account_007", "a2"))
        taken = obs("f1", "2026-04-01T00:00:00Z", "account_service", "account_007", "ABSENT",
                    identifiers=ids(emails=["someone.else@example.com"]))
        self.assertEqual(find(rows, [taken]), ("account_40", "a1"))

    def test_still_ambiguous_chooses_nothing(self):
        rows = [act("a1", "2026-05-01T11:20:00Z", "account_40"), act("a2", "2026-05-01T11:30:00Z", "account_41"),
                act("a3", "2026-05-01T11:35:00Z", "account_7"), act("a4", "2026-05-01T11:40:00Z", "account_07")]
        self.assertIsNone(find(rows))                       # two survivors match user number 7

    def test_other_system_and_operation_by_parameter(self):
        rows = [act("a1", "2026-05-01T11:40:00Z", "analytics_40", event="ANONYMIZE_RECORD",
                    target="analytics_platform"),
                act("a2", "2026-05-01T11:45:00Z", "account_41")]
        f = account_finder.AccountFinder(frame(), activity(*rows), system="analytics_platform",
                                         events=("ANONYMIZE_RECORD",))
        self.assertEqual(f.find(IDENT, REPORTED, AUDIT), ("analytics_40", "a1"))
        self.assertFalse(account_finder.needs({("analytics_platform", "analytics_1"): ["f1"]},
                                              "analytics_platform"))

    def test_needs_account_only_when_none_linked(self):
        self.assertTrue(account_finder.needs_account({("search_service", "search_1"): ["f1"]}))
        self.assertFalse(account_finder.needs_account({("account_service", "account_1"): ["f1"]}))


if __name__ == "__main__":
    unittest.main(verbosity=1)
