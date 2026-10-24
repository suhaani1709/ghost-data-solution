"""Unit tests for the activity treatment signal used as a category fallback.

When no observation of a resource carries a category hint, the treatment
operation the deletion workflow ran on it (DELETE_RECORD / REDACT_RECORD /
ANONYMIZE_RECORD, event_time <= audit_at, result ignored) picks the
category among those the system is seen to hold whose rule action matches.
Ambiguous or missing signals keep the system fallback.

Run:  python3 code/tests/test_category_activity.py
All observations and activity rows here are synthetic; no dataset content.
"""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ghost import state  # noqa: E402
from test_linking_state import frame, obs  # noqa: E402

AUDIT = "2026-03-01T00:00:00Z"
ACTIONS = {"SUPPORT_MESSAGE": "REDACT", "SUPPORT_ATTACHMENT": "DELETE", "USER_PROFILE": "DELETE"}


def act(*rows):
    return pd.DataFrame([{"activity_id": f"a{i}", "event_time": t, "event_type": e,
                          "target_system": "support_platform", "resource_id": r,
                          "reported_result": "SUCCESS"} for i, (t, e, r) in enumerate(rows)])


def resolver(activity):
    df = frame(
        obs("f1", "2026-01-01T00:00:00Z", "support_platform", "support_1", "PRESENT",
            category="SUPPORT_MESSAGE"),
        obs("f1", "2026-01-01T00:00:00Z", "support_platform", "support_2", "PRESENT",
            category="SUPPORT_ATTACHMENT"),
        obs("f2", "2026-01-02T00:00:00Z", "support_platform", "support_9", "PRESENT"))
    return state.StateResolver(df, activity=activity, actions=ACTIONS)


class ActivityCategoryTest(unittest.TestCase):
    def test_delete_operation_picks_the_delete_category(self):
        r = resolver(act(("2026-02-01T00:00:00Z", "DELETE_RECORD", "support_9")))
        self.assertEqual(r.category("support_platform", "support_9", AUDIT), "SUPPORT_ATTACHMENT")
        self.assertEqual((r.fallbacks, r.activity_categories), (0, 1))

    def test_redact_operation_picks_the_redact_category(self):
        r = resolver(act(("2026-02-01T00:00:00Z", "REDACT_RECORD", "support_9")))
        self.assertEqual(r.category("support_platform", "support_9", AUDIT), "SUPPORT_MESSAGE")

    def test_operation_after_audit_is_ignored(self):
        r = resolver(act(("2026-04-01T00:00:00Z", "DELETE_RECORD", "support_9")))
        self.assertEqual(r.category("support_platform", "support_9", AUDIT), "SUPPORT_MESSAGE")
        self.assertEqual(r.fallbacks, 1)

    def test_conflicting_operations_keep_system_fallback(self):
        r = resolver(act(("2026-02-01T00:00:00Z", "DELETE_RECORD", "support_9"),
                         ("2026-02-02T00:00:00Z", "REDACT_RECORD", "support_9")))
        self.assertEqual(r.category("support_platform", "support_9", AUDIT), "SUPPORT_MESSAGE")
        self.assertEqual(r.fallbacks, 1)

    def test_hint_beats_activity(self):
        r = resolver(act(("2026-02-01T00:00:00Z", "DELETE_RECORD", "support_1")))
        self.assertEqual(r.category("support_platform", "support_1", AUDIT), "SUPPORT_MESSAGE")
        self.assertEqual(r.activity_categories, 0)

    def test_no_activity_frame_keeps_system_fallback(self):
        r = resolver(None)
        self.assertEqual(r.category("support_platform", "support_9", AUDIT), "SUPPORT_MESSAGE")


if __name__ == "__main__":
    unittest.main(verbosity=1)
