"""Unit tests for "any copy present" across primary / replica copies.

Rule: within one file, and across files of the same capture time, a resource
is PRESENT if any copy holds it. A replica that kept the row while its
primary in the same file lost it (replication drift) stays PRESENT past later
snapshots that do not capture that replica, until a later replica capture of
the same system shows the row gone or compliant. The citation is the file
whose copy proves presence.

Run:  python3 code/tests/test_replica_drift.py
All observations here are synthetic; no dataset content.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ghost import state  # noqa: E402
from test_absence_proof import cover  # noqa: E402
from test_linking_state import frame, obs  # noqa: E402

SYS, RID = "account_service", "account_2"
T1, T2, T3 = "2026-01-10T00:00:00Z", "2026-02-01T00:00:00Z", "2026-02-15T00:00:00Z"
AUDIT = "2026-03-01T00:00:00Z"


def row(file_id, t, rid, state_, copy):
    return obs(file_id, t, SYS, rid, state_, category="USER_PROFILE", copy=copy, kind="sql")


def drift_file(file_id="f1", t=T1):
    """Primary lost account_2, replica still holds it (account_9 is in both)."""
    return [row(file_id, t, "account_9", "PRESENT", "primary"),
            row(file_id, t, "account_9", "PRESENT", "replica"),
            row(file_id, t, RID, "PRESENT", "replica")]


def resolve(*rows, mode="drift"):
    return state.StateResolver(frame(*rows), replica_persist=mode).resolve(SYS, RID, AUDIT)


class ReplicaDriftTest(unittest.TestCase):
    def test_one_file_any_copy_present(self):
        st = resolve(*drift_file())
        self.assertEqual((st.state, st.evidence_id, st.copy), ("PRESENT", "f1", "replica"))

    def test_same_capture_time_across_files_any_copy_present(self):
        st = resolve(row("f1", T2, RID, "ABSENT", "primary"),
                     row("f2", T2, RID, "PRESENT", "replica"))
        self.assertEqual((st.state, st.evidence_id), ("PRESENT", "f2"))

    def test_drifted_replica_survives_later_primary_absence(self):
        st = resolve(*drift_file(), cover("f2", T2),
                     row("f2", T2, "account_9", "PRESENT", "unknown"))
        self.assertEqual((st.state, st.evidence_id), ("PRESENT", "f1"))

    def test_drifted_replica_survives_later_redacted_primary_row(self):
        st = resolve(*drift_file(), row("f2", T2, RID, "REDACTED", "primary"))
        self.assertEqual((st.state, st.evidence_id), ("PRESENT", "f1"))

    def test_later_replica_capture_without_the_row_ends_it(self):
        st = resolve(*drift_file(), cover("f2", T2),
                     row("f3", T3, "account_9", "PRESENT", "replica"))
        self.assertEqual((st.state, st.evidence_id), ("ABSENT", "f2"))

    def test_later_replica_capture_showing_compliant_ends_it(self):
        st = resolve(*drift_file(), cover("f2", T2), row("f3", T3, RID, "ABSENT", "replica"))
        self.assertEqual(st.state, "ABSENT")

    def test_replica_capture_after_audit_is_ignored(self):
        st = resolve(*drift_file(), cover("f2", T2),
                     row("f9", "2026-04-01T00:00:00Z", "account_9", "PRESENT", "replica"))
        self.assertEqual((st.state, st.evidence_id), ("PRESENT", "f1"))

    def test_no_drift_when_primary_also_held_the_row(self):
        rows = [row("f1", T1, RID, "PRESENT", "primary"), row("f1", T1, RID, "PRESENT", "replica"),
                cover("f2", T2)]
        self.assertEqual(resolve(*rows).state, "ABSENT")
        self.assertEqual(resolve(*rows, mode="any").state, "PRESENT")

    def test_off_keeps_latest_file_rule(self):
        st = resolve(*drift_file(), cover("f2", T2), mode="off")
        self.assertEqual((st.state, st.evidence_id), ("ABSENT", "f2"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
