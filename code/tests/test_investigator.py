"""Unit tests for the investigator agent loop and its deterministic merge checks.

A fake client plays the model, so no model is called.

Run:  python3 code/tests/test_investigator.py
All inputs here are synthetic; no dataset content.
"""
import json
import sys
import unittest
from collections import namedtuple
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghost import account_finder, investigator, llm, loaders, planner, state  # noqa: E402
from test_linking_state import IDENT, frame, ids, obs  # noqa: E402

Case = namedtuple("Case", "case_id email requested_at reported_status reported_at audit_at request_text")
CASE = Case("c1", "new@example.com", "2026-04-30T00:00:00Z", "COMPLETE", "2026-05-01T12:00:00Z",
            "2026-05-10T00:00:00Z", "Please delete my account.")
TREAT = planner.load_treatments()
RULES = loaders.load_deletion_rules()


def activity(*rows):
    return pd.DataFrame([{"activity_id": a, "event_time": t, "event_type": "DELETE_RECORD",
                          "source_system": "deletion_worker", "target_system": "account_service",
                          "resource_id": r, "reported_result": "SUCCESS", "details": ""}
                         for a, t, r in rows], columns=loaders.ACTIVITY_COLUMNS)


def tools(obs_rows=(), act_rows=()):
    df, act = frame(*obs_rows), activity(*act_rows)
    return investigator.CaseTools(
        obs=df, activity=act, resolver=state.StateResolver(df),
        finder=account_finder.AccountFinder(df, act), treatments=TREAT, rules=RULES,
        manifest=pd.DataFrame({"file_id": ["f1"], "file_path": ["x.json"], "origin": ["o"],
                               "captured_at": ["2026-04-01T00:00:00Z"]}),
        ident=IDENT, case=CASE, owner={})


class FakeClient:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.seen = []

    def chat(self, messages, purpose, max_tokens=2000):
        self.seen.append(list(messages))
        if not self.answers:
            raise llm.LLMUnavailable("done")
        return self.answers.pop(0)


def act_json(action, **args):
    return json.dumps({"thought": "t", "action": action, "args": args})


def entry(s, r, audit, category=None):
    return (s, r, category or ("USER_PROFILE" if s == "account_service" else "SUPPORT_MESSAGE"),
            "ABSENT" if s == "account_service" else "PRESENT", "f1")


SUPPORT = ("support_platform", "support_1", "SUPPORT_MESSAGE", "PRESENT", "f1")


class LoopTest(unittest.TestCase):
    def test_tool_then_submit(self):
        t = tools([obs("f1", "2026-04-01T00:00:00Z", "support_platform", "support_1", "IDENTIFIABLE",
                       identifiers=ids(emails=["new@example.com"]))])
        fake = FakeClient(act_json("record_history", system_id="support_platform", resource_id="support_1"),
                          act_json("submit", records=[{"system_id": "support_platform", "resource_id": "support_1",
                                                       "decision": "keep", "category": "SUPPORT_ATTACHMENT",
                                                       "reason": "file"}], confidence="high", summary="s"))
        rv = investigator.Investigator(fake).review(CASE, IDENT, {}, [SUPPORT], t)
        self.assertEqual((rv.status, rv.steps, rv.tool_calls), ("submitted", 2, ["record_history"]))
        self.assertIn('"tool": "record_history"', fake.seen[1][-1]["content"])
        self.assertEqual(rv.proposals[0].category, "SUPPORT_ATTACHMENT")

    def test_malformed_replies_count_and_cap_keeps_baseline(self):
        fake = FakeClient("not json", "still not json")
        rv = investigator.Investigator(fake, max_steps=2).review(CASE, IDENT, {}, [SUPPORT], tools())
        self.assertEqual(rv.status, "cap_reached")
        self.assertIn("error", fake.seen[1][-1]["content"])
        self.assertEqual(investigator.merge([SUPPORT], rv, tools(), entry, TREAT, {"drop"}), [SUPPORT])

    def test_unavailable_model_keeps_baseline(self):
        rv = investigator.Investigator(FakeClient()).review(CASE, IDENT, {}, [SUPPORT], tools())
        self.assertEqual(rv.status, "unavailable")


def submitted(*records):
    rv = investigator.Review("c1", status="submitted")
    rv.proposals = investigator.parse_proposals(list(records))
    return rv


class MergeTest(unittest.TestCase):
    ALL = {"add_account", "drop", "recategorize"}

    def test_account_added_only_from_shown_candidates_when_none_exists(self):
        t = tools(act_rows=[("a1", "2026-05-01T11:30:00Z", "account_40")])
        add = {"system_id": "account_service", "resource_id": "account_40", "decision": "add"}
        rv = submitted(add)
        self.assertEqual(investigator.merge([SUPPORT], rv, t, entry, TREAT, self.ALL), [SUPPORT])  # not shown
        t.account_candidates()
        out = investigator.merge([SUPPORT], submitted(add), t, entry, TREAT, self.ALL)
        self.assertIn(("account_service", "account_40", "USER_PROFILE", "ABSENT", "f1"), out)
        has = [("account_service", "account_1", "USER_PROFILE", "ABSENT", "f1"), SUPPORT]
        self.assertEqual(investigator.merge(has, submitted(add), t, entry, TREAT, self.ALL), has)
        rv = submitted(add)
        self.assertEqual(investigator.merge([SUPPORT], rv, t, entry, TREAT, {"drop"}), [SUPPORT])
        self.assertIn("only account additions", rv.rejected[0])

    def test_drop_refused_when_own_evidence_names_the_requester(self):
        strong = tools([obs("f1", "2026-04-01T00:00:00Z", "support_platform", "support_1", "IDENTIFIABLE",
                            identifiers=ids(emails=["new@example.com"]))])
        drop = {"system_id": "support_platform", "resource_id": "support_1", "decision": "drop"}
        rv = submitted(drop)
        self.assertEqual(investigator.merge([SUPPORT], rv, strong, entry, TREAT, self.ALL), [SUPPORT])
        self.assertTrue(rv.rejected)
        weak = tools([obs("f1", "2026-04-01T00:00:00Z", "support_platform", "support_1", "PRESENT")])
        self.assertEqual(investigator.merge([SUPPORT], submitted(drop), weak, entry, TREAT, self.ALL), [])

    def test_recategorize_only_to_a_supported_category(self):
        t = tools()
        ok = submitted({"system_id": "support_platform", "resource_id": "support_1", "decision": "keep",
                        "category": "SUPPORT_ATTACHMENT"})
        self.assertEqual(investigator.merge([SUPPORT], ok, t, entry, TREAT, self.ALL)[0][2], "SUPPORT_ATTACHMENT")
        bad = submitted({"system_id": "support_platform", "resource_id": "support_1", "decision": "keep",
                         "category": "USER_PROFILE"})
        self.assertEqual(investigator.merge([SUPPORT], bad, t, entry, TREAT, self.ALL), [SUPPORT])
        self.assertIn("not supported", bad.rejected[0])

    def test_unknown_decisions_are_ignored(self):
        self.assertEqual(investigator.parse_proposals([{"system_id": "a", "resource_id": "b", "decision": "nuke"},
                                                       "junk", {"system_id": "a"}]), [])



class RoutingTest(unittest.TestCase):
    def test_flags(self):
        df = frame(obs("f1", "2026-04-01T00:00:00Z", "support_platform", "support_1", "PRESENT", category="SUPPORT_MESSAGE"),
                   obs("f2", "2026-04-02T00:00:00Z", "support_platform", "support_1", "PRESENT", category="SUPPORT_ATTACHMENT"))
        acct = ("account_service", "account_1", "USER_PROFILE", "ABSENT", "f1")
        self.assertEqual(investigator.uncertainty_flags({("support_platform", "support_1"): ["f1"]}, [SUPPORT], df),
                         ["category_conflict", "no_account"])
        self.assertEqual(investigator.uncertainty_flags({("account_service", "account_1"): ["activity_9"]}, [acct], df),
                         ["weak_link"])
        self.assertEqual(investigator.uncertainty_flags({}, [], df), [])          # nothing to review

    def test_route_by_priority_then_case_order_within_budget(self):
        flags = {"case_10": ["no_account"], "case_9": ["weak_link"], "case_100": ["category_conflict"],
                 "case_2": [], "case_3": ["no_account", "weak_link"]}
        self.assertEqual(investigator.route(flags, 3), ["case_100", "case_3", "case_9"])
        self.assertEqual(investigator.route(flags, 0), [])
        self.assertEqual(investigator.route(flags, None), ["case_100", "case_3", "case_9", "case_10"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
