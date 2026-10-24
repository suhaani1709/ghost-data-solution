"""Unit tests for one-hop reference following in linking.py.

Run:  python3 -m unittest code/tests/test_reference_following.py -v
All observations and activity rows here are synthetic; no dataset content.
"""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ghost import linking, loaders, parse_common  # noqa: E402
from test_linking_state import EMAIL_NEW, IDENT, frame, ids, obs  # noqa: E402

AUDIT = "2026-02-01T00:00:00Z"


def ref(file_id, captured_at, resource_id, owner):
    row = obs(file_id, captured_at, parse_common.system_for(resource_id), resource_id, "REFERENCED")
    row["referenced_by"] = owner
    return row


def activity(*rows):
    cols = loaders.ACTIVITY_COLUMNS
    return pd.DataFrame([dict(zip(cols, r)) for r in rows], columns=cols)


def act(activity_id, event_time, resource_id, details):
    return (activity_id, event_time, "SYNC_RECORD", "integration_service", "search_service",
            resource_id, "SUCCESS", details)


class ReferenceFollowingTest(unittest.TestCase):
    def test_reference_unit_records_its_owner(self):
        units = parse_common.reference_units('{"resource_id": "search_1", "source_resource_id": '
                                             '"account_9"}', ["search_1"])
        self.assertEqual([(u["resource_id"], u["referenced_by"]) for u in units],
                         [("account_9", "search_1")])

    def test_follows_reference_from_linked_owner(self):
        df = frame(obs("f1", "2026-01-01T00:00:00Z", "search_service", "search_1", "PRESENT",
                       identifiers=ids(emails=[EMAIL_NEW])),
                   ref("f1", "2026-01-01T00:00:00Z", "account_9", "search_1"))
        linked = linking.Linker(df, follow=True).link(IDENT, AUDIT)
        self.assertEqual(linked[("account_service", "account_9")], ["f1"])

    def test_off_by_default(self):
        df = frame(obs("f1", "2026-01-01T00:00:00Z", "search_service", "search_1", "PRESENT",
                       identifiers=ids(emails=[EMAIL_NEW])),
                   ref("f1", "2026-01-01T00:00:00Z", "account_9", "search_1"))
        self.assertNotIn(("account_service", "account_9"), linking.Linker(df).link(IDENT, AUDIT))

    def test_never_starts_from_unlinked_owner(self):
        df = frame(obs("f1", "2026-01-01T00:00:00Z", "search_service", "search_1", "PRESENT",
                       identifiers=ids(emails=["other@example.com"])),
                   ref("f1", "2026-01-01T00:00:00Z", "account_9", "search_1"))
        self.assertEqual(linking.Linker(df, follow=True).link(IDENT, AUDIT), {})

    def test_reference_captured_after_audit_is_ignored(self):
        df = frame(obs("f1", "2026-01-01T00:00:00Z", "search_service", "search_1", "PRESENT",
                       identifiers=ids(emails=[EMAIL_NEW])),
                   ref("f2", "2026-03-01T00:00:00Z", "account_9", "search_1"))
        self.assertEqual(sorted(linking.Linker(df, follow=True).link(IDENT, AUDIT)),
                         [("search_service", "search_1")])

    def test_one_hop_only(self):
        df = frame(obs("f1", "2026-01-01T00:00:00Z", "search_service", "search_1", "PRESENT",
                       identifiers=ids(emails=[EMAIL_NEW])),
                   ref("f1", "2026-01-01T00:00:00Z", "account_9", "search_1"),
                   ref("f2", "2026-01-02T00:00:00Z", "backup_4", "account_9"))
        linked = linking.Linker(df, follow=True).link(IDENT, AUDIT)
        self.assertIn(("account_service", "account_9"), linked)
        self.assertNotIn(("backup_service", "backup_4"), linked)

    def test_activity_downstream_row_from_linked_flow(self):
        df = frame(obs("f1", "2026-01-01T00:00:00Z", "integration_service", "data_flow_3", "ACTIVE",
                       identifiers=ids(user_ids=["user_7"])))
        acts = activity(
            act("activity_1", "2026-01-05T00:00:00Z", "data_flow_3",
                "Active connector repopulated downstream resource search_8."),
            act("activity_2", "2026-03-05T00:00:00Z", "data_flow_3",          # after audit_at
                "Active connector repopulated downstream resource search_9."),
            act("activity_3", "2026-01-05T00:00:00Z", "data_flow_4",          # unlinked flow
                "Active connector repopulated downstream resource search_10."))
        linked = linking.Linker(df, activity=acts, follow=True).link(IDENT, AUDIT)
        self.assertEqual(sorted(linked), [("integration_service", "data_flow_3"),
                                          ("search_service", "search_8")])
        self.assertEqual(linked[("search_service", "search_8")], ["activity_1"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
