"""Unit tests for account_finder.py: one account record per deletion case.

Used only when linking found no account_service resource. Candidates are
account_service DELETE_RECORD activity rows in the window around reported_at
(<= audit_at). Accounts that evidence (<= audit_at, not a mere REFERENCED
mention) ties to an identifier other than the subject's are removed. The
user-number pattern only breaks ties among survivors; still ambiguous -> None.

Run:  python3 code/tests/test_account_finder.py
All inputs here are synthetic; no dataset content.
"""
import dataclasses
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

    def test_windows_are_fallbacks_in_order(self):
        rows = [act("a1", "2026-05-01T11:00:00Z", "account_40"),     # 60 min before the report
                act("a2", "2026-05-01T11:50:00Z", "account_41"),     # 10 min before: outside both
                act("a3", "2026-05-01T12:03:00Z", "account_42")]     # 3 min after: near window only
        f = account_finder.AccountFinder(frame(), activity(*rows), windows=((76, -39), (6, 6)))
        self.assertEqual(f.find(IDENT, REPORTED, AUDIT), ("account_40", "a1"))     # first window wins
        f = account_finder.AccountFinder(frame(), activity(rows[1], rows[2]), windows=((76, -39), (6, 6)))
        self.assertEqual(f.find(IDENT, REPORTED, AUDIT), ("account_42", "a3"))     # empty first -> next

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

    def test_later_account_dropped_when_one_is_linked_before_audit(self):
        linked = {("account_service", "account_1"): ["f1"], ("account_service", "account_2"): ["f9"],
                  ("search_service", "search_1"): ["f9"]}
        before = {("account_service", "account_1"): ["f1"]}
        self.assertEqual(sorted(account_finder.one_account(linked, before)),
                         [("account_service", "account_1"), ("search_service", "search_1")])
        # no account before audit_at: the later one is the only evidence and stays
        self.assertEqual(account_finder.one_account(linked, {}), linked)

    def test_reported_status_must_match_the_delete_result(self):
        rows = [dict(act("a1", "2026-05-01T11:20:00Z", "account_40"), reported_result="FAILED"),
                dict(act("a2", "2026-05-01T11:30:00Z", "account_41"), reported_result="SUCCESS")]
        f = account_finder.AccountFinder(frame(), activity(*rows), status_match=True)
        self.assertEqual(f.find(IDENT, REPORTED, AUDIT, reported_status="COMPLETE"), ("account_41", "a2"))
        self.assertEqual(f.find(IDENT, REPORTED, AUDIT, reported_status="NOT_STARTED"), ("account_40", "a1"))
        self.assertIsNone(f.find(IDENT, REPORTED, AUDIT))                     # no status: both survive

    def test_newest_pre_audit_account_wins(self):
        linked = {("account_service", "account_old"): ["f_mar"], ("account_service", "account_new"): ["f_sep"],
                  ("search_service", "search_1"): ["f_sep"]}
        cap = {"f_mar": "2026-03-10T00:00:00Z", "f_sep": "2026-09-15T00:00:00Z"}
        self.assertEqual(sorted(account_finder.newest_account(linked, linked, cap, "2026-09-15T12:00:00Z")),
                         [("account_service", "account_new"), ("search_service", "search_1")])
        before = {("account_service", "account_old"): ["f_mar"]}          # audit in March: only the old one
        self.assertEqual(sorted(account_finder.newest_account(linked, before, cap, "2026-03-11T00:00:00Z")),
                         [("account_service", "account_old"), ("search_service", "search_1")])

    def test_status_match_only_in_primary_window_when_configured(self):
        rows = [dict(act("a1", "2026-05-01T12:03:00Z", "account_40"), reported_result="SUCCESS")]   # +3 min
        strict = account_finder.AccountFinder(frame(), activity(*rows), windows=((76, -39), (6, 6)), status_match=True)
        self.assertIsNone(strict.find(IDENT, REPORTED, AUDIT, reported_status="PARTIALLY_COMPLETE"))
        primary = account_finder.AccountFinder(frame(), activity(*rows), windows=((76, -39), (6, 6)),
                                               status_match=True, status_windows=1)
        self.assertEqual(primary.find(IDENT, REPORTED, AUDIT, reported_status="PARTIALLY_COMPLETE"), ("account_40", "a1"))

    def test_needs_account_only_when_none_linked(self):
        self.assertTrue(account_finder.needs_account({("search_service", "search_1"): ["f1"]}))
        self.assertFalse(account_finder.needs_account({("account_service", "account_1"): ["f1"]}))



def ident(n):
    return dataclasses.replace(IDENT, user_id=f"user_{n}")


def pool_case(case_id, n, account=None, reported=REPORTED):
    return account_finder.PoolCase(case_id, ident(n), reported, AUDIT, account)


class PropagationTest(unittest.TestCase):
    def setUp(self):
        self.rows = [act("a1", "2026-05-01T11:20:00Z", "account_40"),
                     act("a2", "2026-05-01T11:30:00Z", "account_41"),
                     act("a3", "2026-05-01T11:40:00Z", "account_42")]
        self.finder = account_finder.AccountFinder(frame(), activity(*self.rows))

    def test_taken_accounts_leave_other_pools_round_by_round(self):
        # c1's only candidate (in its own window) is account_40; c2 then has account_41 left.
        early = "2026-05-01T11:25:00Z"     # window of c1 covers 10:10-11:35 -> account_40, account_41
        cases = [pool_case("c0", 50, account="account_41"),            # linked by evidence
                 pool_case("c1", 51, reported=early),
                 pool_case("c2", 52)]
        picks, rounds = account_finder.propagate(cases, self.finder)
        self.assertEqual(picks, {"c1": ("account_40", "a1"), "c2": ("account_42", "a3")})
        self.assertEqual([sorted(r) for r in rounds], [["c1"], ["c2"]])

    def test_same_round_conflict_between_users_picks_nothing(self):
        f = account_finder.AccountFinder(frame(), activity(self.rows[0]))
        picks, _ = account_finder.propagate([pool_case("c1", 51), pool_case("c2", 52)], f)
        self.assertEqual(picks, {})

    def test_same_user_may_share_its_account(self):
        f = account_finder.AccountFinder(frame(), activity(self.rows[0]))
        picks, _ = account_finder.propagate([pool_case("c1", 51), pool_case("c2", 51)], f)
        self.assertEqual(picks, {"c1": ("account_40", "a1"), "c2": ("account_40", "a1")})

    def test_still_ambiguous_stays_unpicked(self):
        picks, rounds = account_finder.propagate([pool_case("c1", 51)], self.finder)
        self.assertEqual((picks, rounds), ({}, []))

    def test_rank_closest_to_reported_then_user_number(self):
        rows = [act("a1", "2026-05-01T11:20:00Z", "account_40"),
                act("a2", "2026-05-01T11:50:00Z", "account_41"),
                act("a3", "2026-05-01T12:10:00Z", "account_7")]
        f = account_finder.AccountFinder(frame(), activity(*rows))
        ranked = f.rank(f.survivors(IDENT, REPORTED, AUDIT), "user_7")
        self.assertEqual([r for r, _ in ranked], ["account_7", "account_41", "account_40"])
        self.assertEqual([m for _, m in ranked], [10.0, 10.0, 40.0])
        self.assertEqual(f.rank(f.survivors(IDENT, REPORTED, AUDIT), "user_41")[0][0], "account_41")


if __name__ == "__main__":
    unittest.main(verbosity=1)
