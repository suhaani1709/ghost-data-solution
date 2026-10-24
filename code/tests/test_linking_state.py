"""Unit tests for linking.py (v0 exact matching) and state.py (state at audit_at).

Run:  python3 -m unittest code/tests/test_linking_state.py -v
All observations here are synthetic; no dataset content.
"""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghost import identity, linking, observations, planner, state  # noqa: E402

EMAIL_OLD, EMAIL_NEW = "old@example.com", "new@example.com"
IDENT = identity.IdentitySet(
    user_id="user_7", name="Ada Example", email=EMAIL_NEW, phone="+1 555 0100",
    email_hash=identity.email_sha256(EMAIL_NEW),
    emails=frozenset({EMAIL_OLD, EMAIL_NEW}), historical_emails=frozenset({EMAIL_OLD}),
    phones=frozenset({"+1 555 0100"}),
    email_hashes=frozenset({identity.email_sha256(EMAIL_OLD), identity.email_sha256(EMAIL_NEW)}))


def ids(emails=(), hashes=(), phones=(), user_ids=()):
    return {"emails": sorted(emails), "hashes": sorted(hashes), "phones": sorted(phones),
            "user_ids": sorted(user_ids)}


def obs(file_id, captured_at, system_id, resource_id, state_, category="", identifiers=None,
        copy="unknown", kind="json"):
    return {"file_id": file_id, "captured_at": captured_at, "file_kind": kind,
            "system_id": system_id, "resource_id": resource_id, "category_hint": category,
            "state": state_, "identifiers": identifiers or ids(), "copy": copy,
            "event_time": "", "raw_snippet": ""}


def frame(*rows):
    return pd.DataFrame(list(rows), columns=observations.COLUMNS)


class LinkingTest(unittest.TestCase):
    def test_links_by_old_email_hash_phone_and_user_id(self):
        df = frame(
            obs("f1", "2026-01-01T00:00:00Z", "account_service", "account_1", "PRESENT",
                identifiers=ids(emails=[EMAIL_OLD])),
            obs("f1", "2026-01-01T00:00:00Z", "search_service", "search_1", "PRESENT",
                identifiers=ids(hashes=[identity.email_sha256(EMAIL_OLD)])),
            obs("f1", "2026-01-01T00:00:00Z", "support_platform", "support_1", "IDENTIFIABLE",
                identifiers=ids(phones=["+1 555 0100"])),
            obs("f1", "2026-01-01T00:00:00Z", "security_service", "audit_record_1", "PRESENT",
                identifiers=ids(user_ids=["user_7"])),
            obs("f1", "2026-01-01T00:00:00Z", "account_service", "account_2", "PRESENT",
                identifiers=ids(emails=["other@example.com"], user_ids=["user_70"])))
        linked = linking.Linker(df).link(IDENT, "2026-02-01T00:00:00Z")
        self.assertEqual(sorted(linked), [("account_service", "account_1"),
                                          ("search_service", "search_1"),
                                          ("security_service", "audit_record_1"),
                                          ("support_platform", "support_1")])

    def test_ignores_files_after_audit_at(self):
        df = frame(obs("f2", "2026-03-01T00:00:00Z", "account_service", "account_1", "PRESENT",
                       identifiers=ids(emails=[EMAIL_NEW])))
        self.assertEqual(linking.Linker(df).link(IDENT, "2026-02-01T00:00:00Z"), {})

    def test_referenced_rows_do_not_link(self):
        df = frame(obs("f1", "2026-01-01T00:00:00Z", "account_service", "account_1", "REFERENCED",
                       identifiers=ids(emails=[EMAIL_NEW])))
        self.assertEqual(linking.Linker(df).link(IDENT, "2026-02-01T00:00:00Z"), {})

    def test_sticky_after_identifiers_are_nulled(self):
        df = frame(
            obs("f1", "2026-01-01T00:00:00Z", "analytics_platform", "analytics_1", "IDENTIFIABLE",
                identifiers=ids(emails=[EMAIL_NEW])),
            obs("f2", "2026-01-15T00:00:00Z", "analytics_platform", "analytics_1", "ANONYMIZED"))
        linked = linking.Linker(df).link(IDENT, "2026-02-01T00:00:00Z")
        self.assertIn(("analytics_platform", "analytics_1"), linked)


class StateTest(unittest.TestCase):
    def test_latest_file_wins_and_is_cited(self):
        df = frame(
            obs("f1", "2026-01-01T00:00:00Z", "account_service", "account_1", "PRESENT"),
            obs("f2", "2026-01-10T00:00:00Z", "account_service", "account_1", "ABSENT"),
            obs("f3", "2026-03-01T00:00:00Z", "account_service", "account_1", "PRESENT"))
        st = state.StateResolver(df).resolve("account_service", "account_1", "2026-02-01T00:00:00Z")
        self.assertEqual((st.state, st.evidence_id), ("ABSENT", "f2"))

    def test_any_copy_present_is_present(self):
        df = frame(
            obs("f1", "2026-01-01T00:00:00Z", "account_service", "account_1", "ABSENT", copy="primary", kind="sql"),
            obs("f1", "2026-01-01T00:00:00Z", "account_service", "account_1", "PRESENT", copy="replica", kind="sql"))
        st = state.StateResolver(df).resolve("account_service", "account_1", "2026-02-01T00:00:00Z")
        self.assertEqual((st.state, st.evidence_id), ("PRESENT", "f1"))

    def test_covering_snapshot_without_the_row_is_absent(self):
        df = frame(
            obs("f1", "2026-01-01T00:00:00Z", "account_service", "account_1", "PRESENT"),
            obs("f2", "2026-01-20T00:00:00Z", "account_service", "", "", category="USER_PROFILE", kind="sql"))
        st = state.StateResolver(df).resolve("account_service", "account_1", "2026-02-01T00:00:00Z")
        self.assertEqual((st.state, st.evidence_id), ("ABSENT", "f2"))

    def test_category_hint_then_counted_fallback(self):
        df = frame(
            obs("f1", "2026-01-01T00:00:00Z", "analytics_platform", "analytics_1", "PRESENT",
                category="MARKETING_PROFILE"),
            obs("f1", "2026-01-01T00:00:00Z", "support_platform", "support_1", "PRESENT"))
        res = state.StateResolver(df)
        self.assertEqual(res.category("analytics_platform", "analytics_1", "2026-02-01T00:00:00Z"),
                         "MARKETING_PROFILE")
        self.assertEqual(res.category("support_platform", "support_1", "2026-02-01T00:00:00Z"),
                         "SUPPORT_MESSAGE")
        self.assertEqual(res.fallbacks, 1)

    def test_planner_state_maps_observation_vocabulary(self):
        t = planner.load_treatments()
        self.assertEqual(state.planner_state("ANALYTICS_PROFILE", "IDENTIFIABLE", t), "PRESENT")
        self.assertEqual(state.planner_state("SUPPORT_MESSAGE", "REDACTED", t), "REDACTED")
        self.assertEqual(state.planner_state("DATA_FLOW", "ACTIVE", t), "ACTIVE")
        self.assertEqual(state.planner_state("USER_PROFILE", "IDENTIFIABLE", t), "PRESENT")


if __name__ == "__main__":
    unittest.main(verbosity=1)
