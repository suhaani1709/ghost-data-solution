"""Late-export linking: a unit whose own event_time is <= audit_at links even when
its file was captured after audit_at; it is never cited and never changes status.

Run:  python3 -m unittest code/tests/test_late_links.py -v
All observations here are synthetic; no dataset content.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghost import linking, planner, state  # noqa: E402
from tests.test_linking_state import EMAIL_OLD, IDENT, frame, ids, obs  # noqa: E402

AUDIT = "2026-09-16T09:00:00Z"
LATE_FILE = "2026-09-18T11:55:00Z"


def late(file_id, system_id, resource_id, state_, event_time, kind="log", category="",
         identifiers=None, captured_at=LATE_FILE):
    row = obs(file_id, captured_at, system_id, resource_id, state_, category=category,
              identifiers=identifiers, kind=kind)
    row["event_time"] = event_time
    return row


class LateLinksTest(unittest.TestCase):
    def setUp(self):
        self.df = frame(
            # on time: an exposed search entry, linked normally
            obs("f_on", "2026-09-10T00:00:00Z", "search_service", "search_1", "PRESENT",
                identifiers=ids(emails=[EMAIL_OLD])),
            # late file, events before audit_at, carrying the user's tokens
            late("f_late", "security_service", "audit_record_1", "PRESENT", "2026-09-16T08:52:59Z",
                 category="SECURITY_AUDIT_LOG", identifiers=ids(user_ids=["user_7"])),
            late("f_late", "account_service", "account_1", "ABSENT", "2026-09-16T08:57:34Z",
                 category="USER_PROFILE", identifiers=ids(emails=[EMAIL_OLD])),
            # late file, event after audit_at: must not link
            late("f_late", "account_service", "account_2", "ABSENT", "2026-09-17T10:00:00Z",
                 identifiers=ids(emails=[EMAIL_OLD])),
            # late file, event before audit_at, but a kind outside late_kinds (pdf has no event time)
            late("f_pdf", "support_platform", "support_1", "IDENTIFIABLE", "2026-09-15T00:00:00Z",
                 kind="pdf", identifiers=ids(emails=[EMAIL_OLD])),
            # late file, other user's tokens: must not link
            late("f_late", "security_service", "audit_record_2", "PRESENT", "2026-09-16T08:00:00Z",
                 identifiers=ids(user_ids=["user_70"])))

    def test_normal_link_ignores_late_files(self):
        linker = linking.Linker(self.df, late_kinds=("log",))
        self.assertEqual(list(linker.link(IDENT, AUDIT)), [("search_service", "search_1")])

    def test_late_links_use_event_time_and_kind(self):
        linker = linking.Linker(self.df, late_kinds=("log", "json"))
        found = linker.late_links(IDENT, AUDIT)
        self.assertEqual(sorted(found), [("account_service", "account_1"),
                                         ("security_service", "audit_record_1")])

    def test_late_links_off_by_default_and_exclude(self):
        self.assertEqual(linking.Linker(self.df).late_links(IDENT, AUDIT), {})
        linker = linking.Linker(self.df, late_kinds=("log",))
        found = linker.late_links(IDENT, AUDIT, exclude={("account_service", "account_1")})
        self.assertEqual(list(found), [("security_service", "audit_record_1")])

    def test_resolve_late_state_and_category(self):
        res = state.StateResolver(self.df)
        self.assertEqual(res.resolve_late("security_service", "audit_record_1", AUDIT),
                         ("PRESENT", "SECURITY_AUDIT_LOG"))
        self.assertEqual(res.resolve_late("account_service", "account_1", AUDIT),
                         ("ABSENT", "USER_PROFILE"))
        # event after audit_at -> nothing usable
        self.assertIsNone(res.resolve_late("account_service", "account_2", AUDIT))
        # the normal resolver still sees nothing captured on time for these
        self.assertIsNone(res.resolve("security_service", "audit_record_1", AUDIT))

    def test_late_resources_only_add_uncited_verification(self):
        t = planner.load_treatments()
        on_time = [("search_service", "search_1", "SEARCH_INDEX_ENTRY", "PRESENT", "f_on")]
        late_res = [("security_service", "audit_record_1", "SECURITY_AUDIT_LOG", "PRESENT", "")]
        status, steps = planner.build_steps(on_time + late_res, t)
        self.assertEqual(status, "INCOMPLETE")
        added = [s for s in steps if s["resource_id"] == "audit_record_1"]
        self.assertEqual([(s["operation"], s["evidence_id"]) for s in added],
                         [("VERIFY_RECORD_PRESENT", "")])


if __name__ == "__main__":
    unittest.main()
