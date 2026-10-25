"""Unit tests for absence proof: a snapshot whose snapshot_scope covers a
system and whose rows lack a resource proves that resource ABSENT, cited to
the latest pre-audit covering snapshot.

Run:  python3 code/tests/test_absence_proof.py
All SQL and observations here are synthetic; no dataset content.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ghost import parse_sql, state  # noqa: E402
from test_linking_state import frame, obs  # noqa: E402

SCOPED_SQL = (
    "CREATE TABLE snapshot_scope (origin_system TEXT PRIMARY KEY, captured_at TEXT NOT NULL);\n"
    "CREATE TABLE customer_profiles (resource_id TEXT PRIMARY KEY, customer_reference TEXT, "
    "full_name TEXT, email TEXT, phone TEXT, email_hash TEXT, account_status TEXT, updated_at TEXT);\n"
    "CREATE TABLE customer_search_documents (resource_id TEXT PRIMARY KEY, customer_reference TEXT, "
    "display_name TEXT, email TEXT, phone TEXT, email_hash TEXT, index_name TEXT, updated_at TEXT);\n"
    "CREATE TABLE support_records (resource_id TEXT PRIMARY KEY, customer_reference TEXT, "
    "requester_name TEXT, requester_email TEXT, requester_phone TEXT, message_excerpt TEXT, "
    "updated_at TEXT);\n"
    "INSERT INTO snapshot_scope VALUES ('account_service', '2026-01-10T00:00:00Z');\n"
    "INSERT INTO snapshot_scope VALUES ('search_service', '2026-01-10T00:00:00Z');\n"
    "INSERT INTO customer_profiles VALUES ('account_1', NULL, NULL, 'a@example.com', NULL, NULL, "
    "'ACTIVE', '2026-01-09T00:00:00Z');\n"
    "INSERT INTO support_records VALUES ('support_1', NULL, NULL, 'a@example.com', NULL, 'hi', "
    "'2026-01-09T00:00:00Z');\n")


def parse(sql):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "snap.sql"
        p.write_text(sql, encoding="utf-8")
        return parse_sql.parse_sql(p)


class ScopeCoverageParseTest(unittest.TestCase):
    def test_every_scoped_system_gets_a_coverage_unit(self):
        cover = {u["system_id"] for u in parse(SCOPED_SQL) if u["resource_id"] == ""}
        # account_service has rows, search_service has none: both are covered.
        self.assertEqual(cover, {"account_service", "search_service"})

    def test_unscoped_system_is_not_covered(self):
        cover = {u["system_id"] for u in parse(SCOPED_SQL) if u["resource_id"] == ""}
        self.assertNotIn("support_platform", cover)

    def test_no_scope_table_means_no_coverage(self):
        sql = SCOPED_SQL.replace("INSERT INTO snapshot_scope", "-- ")
        self.assertFalse([u for u in parse(sql) if u["resource_id"] == ""])

    def test_rows_still_parsed(self):
        rids = {u["resource_id"] for u in parse(SCOPED_SQL) if u["resource_id"]}
        self.assertTrue({"account_1", "support_1"} <= rids)


def cover(file_id, captured_at, system_id="account_service"):
    return obs(file_id, captured_at, system_id, "", "", category="USER_PROFILE", kind="sql")


class AbsenceProofStateTest(unittest.TestCase):
    AUDIT = "2026-03-01T00:00:00Z"

    def resolve(self, *rows, resource=("account_service", "account_2")):
        return state.StateResolver(frame(*rows)).resolve(*resource, self.AUDIT)

    def test_non_empty_covering_snapshot_without_the_row_is_absent(self):
        st = self.resolve(
            obs("f1", "2026-01-01T00:00:00Z", "account_service", "account_2", "PRESENT"),
            cover("f2", "2026-02-01T00:00:00Z"),
            obs("f2", "2026-02-01T00:00:00Z", "account_service", "account_9", "PRESENT", kind="sql"))
        self.assertEqual((st.state, st.evidence_id), ("ABSENT", "f2"))

    def test_latest_pre_audit_covering_snapshot_is_cited(self):
        st = self.resolve(
            obs("f1", "2026-01-01T00:00:00Z", "account_service", "account_2", "PRESENT"),
            cover("f2", "2026-01-15T00:00:00Z"),
            cover("f3", "2026-02-15T00:00:00Z"),
            cover("f4", "2026-04-01T00:00:00Z"))          # after audit_at: ignored
        self.assertEqual((st.state, st.evidence_id), ("ABSENT", "f3"))

    def test_snapshot_containing_the_row_is_not_absence(self):
        st = self.resolve(
            cover("f2", "2026-02-01T00:00:00Z"),
            obs("f2", "2026-02-01T00:00:00Z", "account_service", "account_2", "PRESENT", kind="sql"))
        self.assertEqual((st.state, st.evidence_id), ("PRESENT", "f2"))

    def test_snapshot_covering_another_system_is_not_absence(self):
        st = self.resolve(
            obs("f1", "2026-01-01T00:00:00Z", "account_service", "account_2", "PRESENT"),
            cover("f2", "2026-02-01T00:00:00Z", system_id="search_service"))
        self.assertEqual((st.state, st.evidence_id), ("PRESENT", "f1"))

    def test_later_observation_beats_older_covering_snapshot(self):
        st = self.resolve(
            cover("f2", "2026-01-15T00:00:00Z"),
            obs("f3", "2026-02-01T00:00:00Z", "account_service", "account_2", "PRESENT"))
        self.assertEqual((st.state, st.evidence_id), ("PRESENT", "f3"))

    def test_absence_without_any_own_observation(self):
        st = self.resolve(cover("f2", "2026-02-01T00:00:00Z"))
        self.assertEqual((st.state, st.evidence_id), ("ABSENT", "f2"))

    def test_explicit_absence_is_cited_over_a_later_covering_snapshot(self):
        rows = (obs("f1", "2026-01-01T00:00:00Z", "account_service", "account_2", "ABSENT"),
                cover("f2", "2026-02-01T00:00:00Z"))
        st = state.StateResolver(frame(*rows), explicit_absence=True).resolve(
            "account_service", "account_2", self.AUDIT)
        self.assertEqual((st.state, st.evidence_id), ("ABSENT", "f1"))
        st = state.StateResolver(frame(*rows), explicit_absence=False).resolve(
            "account_service", "account_2", self.AUDIT)
        self.assertEqual((st.state, st.evidence_id), ("ABSENT", "f2"))

    def test_explicit_absence_rule_never_keeps_a_present_record(self):
        st = state.StateResolver(frame(
            obs("f1", "2026-01-01T00:00:00Z", "account_service", "account_2", "PRESENT"),
            cover("f2", "2026-02-01T00:00:00Z")), explicit_absence=True).resolve(
            "account_service", "account_2", self.AUDIT)
        self.assertEqual((st.state, st.evidence_id), ("ABSENT", "f2"))

    def test_blanket_snapshot_does_not_override_an_own_observation(self):
        rows = (obs("f1", "2026-01-01T00:00:00Z", "account_service", "account_2", "PRESENT"),
                cover("f2", "2026-02-01T00:00:00Z"))
        st = state.StateResolver(frame(*rows), coverage_only_if_unobserved=True).resolve(
            "account_service", "account_2", self.AUDIT)
        self.assertEqual((st.state, st.evidence_id), ("PRESENT", "f1"))
        st = state.StateResolver(frame(cover("f2", "2026-02-01T00:00:00Z")),
                                 coverage_only_if_unobserved=True).resolve("account_service", "account_2", self.AUDIT)
        self.assertEqual((st.state, st.evidence_id), ("ABSENT", "f2"))      # never observed: coverage proves absence

    def test_json_bundle_proves_absence_only_for_subjects_it_covers(self):
        from test_linking_state import ids
        bundle = obs("f2", "2026-02-01T00:00:00Z", "account_service", "", "", category="USER_PROFILE", kind="json")
        other = obs("f2", "2026-02-01T00:00:00Z", "identity_service", "tombstone_1", "REDACTED",
                    identifiers=ids(user_ids=["user_5"]), kind="json")
        res = state.StateResolver(frame(bundle, other), scoped_bundles=True)
        self.assertIsNone(res.resolve("account_service", "account_2", self.AUDIT, subject={"user_7"}))
        self.assertEqual(res.resolve("account_service", "account_2", self.AUDIT, subject={"user_5"}).state, "ABSENT")

    def test_sql_dump_is_exhaustive_and_overrides_an_earlier_observation(self):
        rows = (obs("f1", "2026-01-01T00:00:00Z", "account_service", "account_2", "PRESENT"),
                cover("f2", "2026-02-01T00:00:00Z"))
        st = state.StateResolver(frame(*rows), scoped_bundles=True).resolve(
            "account_service", "account_2", self.AUDIT, subject={"user_7"})
        self.assertEqual((st.state, st.evidence_id), ("ABSENT", "f2"))

    def test_absence_proof_can_be_disabled_for_retained_records(self):
        df = frame(
            obs("f1", "2026-01-01T00:00:00Z", "security_service", "audit_record_1", "PRESENT"),
            cover("f2", "2026-02-01T00:00:00Z", system_id="security_service"))
        res = state.StateResolver(df)
        st = res.resolve("security_service", "audit_record_1", self.AUDIT, allow_absence=False)
        self.assertEqual((st.state, st.evidence_id), ("PRESENT", "f1"))
        self.assertIsNone(state.StateResolver(frame(df.iloc[1])).resolve(
            "security_service", "audit_record_1", self.AUDIT, allow_absence=False))


if __name__ == "__main__":
    unittest.main(verbosity=1)
