"""Explicit output schemas for the three LLM agents (ghost/schemas.py) and how each agent
treats an answer that fails its schema or asks for review.

Run:  python3 code/tests/test_schemas.py
A fake client plays the model; no model is called. Synthetic data only.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ghost import intent, intent_agent, investigator, schemas, vision_agent  # noqa: E402
from test_agents import ROW, FakeClient  # noqa: E402


class ValidatorTest(unittest.TestCase):
    def test_intent_item(self):
        self.assertEqual(schemas.errors({"id": 1, "label": "DELETE"}, schemas.INTENT_ITEM), [])
        self.assertTrue(schemas.errors({"id": "1", "label": "DELETE"}, schemas.INTENT_ITEM))
        self.assertTrue(schemas.errors({"id": 1, "label": "MAYBE"}, schemas.INTENT_ITEM))
        self.assertTrue(schemas.errors({"label": "DELETE"}, schemas.INTENT_ITEM))

    def test_vision_answer(self):
        self.assertEqual(schemas.errors({"rows": [dict(ROW)]}, schemas.VISION_ANSWER), [])
        self.assertTrue(schemas.errors({"rows": [dict(ROW, state="GONE")]}, schemas.VISION_ANSWER))
        self.assertTrue(schemas.errors({"rows": [dict(ROW, resource_id="acct 5")]}, schemas.VISION_ANSWER))
        self.assertTrue(schemas.errors([dict(ROW)], schemas.VISION_ANSWER))

    def test_investigator_action(self):
        ok = {"thought": "t", "action": "record_history", "args": {"system_id": "a", "resource_id": "b"}}
        self.assertEqual(schemas.errors(ok, schemas.INVESTIGATOR_ACTION), [])
        self.assertTrue(schemas.errors(dict(ok, action="rm_rf"), schemas.INVESTIGATOR_ACTION))
        self.assertTrue(schemas.errors(dict(ok, args="x"), schemas.INVESTIGATOR_ACTION))


class IntentUnsureTest(unittest.TestCase):
    def test_unsure_and_invalid_items_fall_back_to_the_rules_and_are_counted(self):
        unseen_a, unseen_b, unseen_c = "Hmm what about my stuff.", "Unclear request here.", "Third text."
        answer = json.dumps([{"id": 1, "label": "UNSURE", "reason": "no request stated"},
                             {"id": 2, "label": "maybe"}, {"id": 3, "label": "NON_DELETE"}])
        agent = intent_agent.IntentAgent(FakeClient([answer])).prepare([unseen_a, unseen_b, unseen_c])
        self.assertEqual(agent.source[unseen_a], "fallback")
        self.assertEqual(agent.source[unseen_b], "fallback")
        self.assertEqual((agent.label(unseen_c), agent.source[unseen_c]), (intent.NON_DELETE, "llm"))
        self.assertEqual((agent.stats["llm_unsure"], agent.stats["llm_invalid_items"]), (1, 1))


class VisionSchemaTest(unittest.TestCase):
    def run_agent(self, answer):
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "x.png"
            img.write_bytes(b"\x89PNG fake")
            return vision_agent.read_images({"x.png": img}, {"x.png": [dict(ROW)]},
                                            ({"a@example.com"}, set(), {"user_7"}), FakeClient([answer]))

    def test_schema_failure_uses_the_transcript(self):
        rows, report = self.run_agent(json.dumps({"rows": [dict(ROW, state="GONE")]}))
        self.assertEqual(report["x.png"]["status"], "invalid")
        self.assertEqual(rows["x.png"], [dict(ROW)])

    def test_flagged_unreadable_uses_the_transcript(self):
        rows, report = self.run_agent(json.dumps({"rows": [dict(ROW)], "unreadable": ["search_1"]}))
        self.assertEqual(report["x.png"]["status"], "flagged")
        self.assertEqual(rows["x.png"], [dict(ROW)])


class InvestigatorSchemaTest(unittest.TestCase):
    def test_action_with_wrong_shape_is_returned_as_an_error_turn(self):
        from test_investigator import CASE, IDENT, SUPPORT, tools
        bad = json.dumps({"thought": "t", "action": "record_history", "args": "account_1"})
        fake = FakeClient([bad])
        rv = investigator.Investigator(fake, max_steps=1).review(CASE, IDENT, {}, [SUPPORT], tools())
        self.assertEqual(rv.status, "cap_reached")
        self.assertEqual(rv.tool_calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
