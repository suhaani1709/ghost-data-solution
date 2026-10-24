"""Oracle tests for the step planner, using only the public sample answers.

`resources` are reconstructed from each sample answer (perfect linkage), so
these tests check the planner's policy, status and ordering logic in isolation.

Run:  python3 code/tests/test_planner_oracle.py
"""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghost import loaders  # noqa: E402

PHASES = ["FINDING", "REMEDIATION", "VERIFICATION"]
STEP_FIELDS = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}


def operation_table():
    """[(phase, operation, state)] in the order of problem_statement.md."""
    text = (loaders.REPO_ROOT / "problem_statement.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| `(FINDING|REMEDIATION|VERIFICATION)` \| `(\w+)` \| `(\w+)` \|", text, re.M)
    assert len(rows) == 15, rows
    return rows


OP_ORDER = {op: i for i, (_, op, _) in enumerate(operation_table())}


def sort_key(step):
    return (PHASES.index(step["phase"]), OP_ORDER[step["operation"]], step["system_id"], step["resource_id"])


def sample_cases():
    df = loaders.load_sample_output()
    return [(r.case_id, r.deletion_status, json.loads(r.steps_json)) for r in df.itertuples(index=False)]


# Category of a sample resource, read off the answer: (system_id, final state) -> category.
# The final state is the state of the resource's VERIFICATION step.
SAMPLE_CATEGORY = {
    ("account_service", "ABSENT"): "USER_PROFILE",
    ("search_service", "ABSENT"): "SEARCH_INDEX_ENTRY",
    ("export_service", "ABSENT"): "USER_EXPORT",
    ("support_platform", "ABSENT"): "SUPPORT_ATTACHMENT",
    ("support_platform", "REDACTED"): "SUPPORT_MESSAGE",
    ("analytics_platform", "ANONYMIZED"): "ANALYTICS_PROFILE",
    ("analytics_platform", "ABSENT"): "MARKETING_PROFILE",
    ("security_service", "PRESENT"): "SECURITY_AUDIT_LOG",
    ("identity_service", "REDACTED"): "ACCOUNT_TOMBSTONE",
    ("backup_service", "BLOCKED"): "BACKUP_ARCHIVE",
    ("integration_service", "DISABLED"): "DATA_FLOW",
}


def resources_from_answer(steps):
    """[(system_id, resource_id, category, observed_state, evidence_id)] from a sample answer.

    observed_state / evidence_id come from the FINDING step when there is one
    (non-compliant resource), otherwise from the VERIFICATION step.
    """
    final, finding = {}, {}
    for s in steps:
        key = (s["system_id"], s["resource_id"])
        if s["phase"] == "VERIFICATION":
            final[key] = s
        elif s["phase"] == "FINDING":
            finding[key] = s
    out = []
    for key, v in sorted(final.items()):
        src = finding.get(key, v)
        out.append((key[0], key[1], SAMPLE_CATEGORY[(key[0], v["state"])], src["state"], src["evidence_id"]))
    return out


class SampleOrderTests(unittest.TestCase):
    def test_samples_are_sorted_by_phase_operation_system_resource(self):
        for case_id, _, steps in sample_cases():
            with self.subTest(case_id=case_id):
                self.assertEqual(steps, sorted(steps, key=sort_key))
                self.assertEqual([s["step_no"] for s in steps], list(range(1, len(steps) + 1)))


class PlannerOracleTests(unittest.TestCase):
    def test_planner_operation_table_matches_problem_statement(self):
        from ghost import planner
        self.assertEqual(list(planner.OPERATIONS), operation_table())

    def test_build_steps_reproduces_samples(self):
        from ghost import planner
        for case_id, status, steps in sample_cases():
            with self.subTest(case_id=case_id):
                got_status, got_steps = planner.build_steps(resources_from_answer(steps))
                self.assertEqual(got_status, status)
                for s in got_steps:
                    self.assertEqual(set(s), STEP_FIELDS)
                self.assertEqual(got_steps, steps)

    def test_resource_order_does_not_matter(self):
        from ghost import planner
        for case_id, _, steps in sample_cases():
            with self.subTest(case_id=case_id):
                res = resources_from_answer(steps)
                self.assertEqual(planner.build_steps(res), planner.build_steps(res[::-1]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
