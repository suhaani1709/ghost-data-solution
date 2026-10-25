"""Unit tests for the LLM agents (intent_agent, vision_agent) and the llm cache.

A fake client stands in for OpenRouter, so no network call is made.

Run:  python3 code/tests/test_agents.py
All inputs here are synthetic; no dataset content.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghost import intent, intent_agent, llm, vision_agent  # noqa: E402

KNOWN_DELETE = "Please erase the account linked to this email address."
KNOWN_KEEP = "Please stop the promotional emails."
UNSEEN = "I want this profile gone for good."
UNSEEN_REFUSAL = "Please do not delete my account. I still use it."


class FakeClient:
    def __init__(self, answers):
        self.answers = list(answers)
        self.prompts = []

    def chat(self, messages, purpose, max_tokens=4000):
        self.prompts.append(messages)
        if not self.answers:
            raise llm.LLMUnavailable("no more answers")
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


def labels(*pairs):
    return json.dumps([{"id": i, "label": l} for i, l in pairs])


class IntentAgentTest(unittest.TestCase):
    def test_tables_win_llm_decides_unknown_and_disagreements_are_counted(self):
        texts = [KNOWN_DELETE, KNOWN_KEEP, UNSEEN]
        fake = FakeClient([labels((1, "DELETE"), (2, "DELETE"), (3, "DELETE"))])
        agent = intent_agent.IntentAgent(fake).prepare(texts)
        self.assertEqual([agent.label(t) for t in texts], [intent.DELETE, intent.NON_DELETE, intent.DELETE])
        self.assertEqual(agent.source[UNSEEN], "llm")
        self.assertEqual(agent.stats["table_llm_disagree"], 1)

    def test_explicit_refusal_beats_the_llm(self):
        agent = intent_agent.IntentAgent(FakeClient([labels((1, "DELETE"))])).prepare([UNSEEN_REFUSAL])
        self.assertEqual((agent.label(UNSEEN_REFUSAL), agent.source[UNSEEN_REFUSAL]),
                         (intent.NON_DELETE, "negation"))

    def test_batches_and_duplicates(self):
        texts = [f"Unseen request number {i}." for i in range(5)] * 2
        fake = FakeClient([labels((1, "DELETE"), (2, "DELETE")), labels((1, "NON_DELETE"), (2, "DELETE")),
                           labels((1, "DELETE"))])
        agent = intent_agent.IntentAgent(fake, batch=2).prepare(texts)
        self.assertEqual(len(fake.prompts), 3)
        self.assertEqual(agent.label("Unseen request number 2."), intent.NON_DELETE)

    def test_unavailable_or_malformed_answer_falls_back_to_rules(self):
        for answer in (llm.LLMUnavailable("down"), "not json", labels((1, "MAYBE"))):
            agent = intent_agent.IntentAgent(FakeClient([answer])).prepare([UNSEEN])
            self.assertEqual((agent.label(UNSEEN), agent.source[UNSEEN]), (intent.DELETE, "fallback"))

    def test_text_never_prepared_uses_rules(self):
        agent = intent_agent.IntentAgent(FakeClient([])).prepare([])
        self.assertEqual(agent.label(KNOWN_KEEP), intent.NON_DELETE)


ROW = {"row": "1", "system_id": "search_service", "resource_id": "search_1", "role": "OWN",
       "user_id": "user_7", "email": "a@example.com", "phone": "", "state": "PRESENT",
       "category": "SEARCH_INDEX_ENTRY"}


class VisionAgentTest(unittest.TestCase):
    def setUp(self):
        self.universe = ({"a@example.com"}, set(), {"user_7"})
        self.hand = {"x.png": [dict(ROW)]}

    def run_agent(self, answer):
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "x.png"
            img.write_bytes(b"\x89PNG fake")
            return vision_agent.read_images({"x.png": img}, self.hand, self.universe,
                                            FakeClient([answer]))

    def test_agreeing_reading_is_used(self):
        rows, report = self.run_agent(json.dumps({"rows": [dict(ROW, row="first", email="A@example.com")]}))
        self.assertEqual(report["x.png"]["status"], "agree")
        self.assertEqual(rows["x.png"][0]["row"], "first")

    def test_disagreeing_or_invented_reading_falls_back_to_hand_transcript(self):
        cases = [dict(ROW, state="ABSENT"), dict(ROW, email="b@example.com"), dict(ROW, resource_id="search_2")]
        for bad in cases:
            rows, report = self.run_agent(json.dumps({"rows": [bad]}))
            self.assertEqual(report["x.png"]["status"], "disagree", bad)
            self.assertEqual(rows["x.png"], self.hand["x.png"])

    def test_identifier_outside_identities_agrees_when_the_transcript_has_it_too(self):
        decoy = dict(ROW, email="lookalike@example.com")        # e.g. a decoy shown on screen
        self.hand = {"x.png": [dict(decoy)]}
        rows, report = self.run_agent(json.dumps({"rows": [dict(decoy)]}))
        self.assertEqual((report["x.png"]["status"], report["x.png"]["outside_identities"]), ("agree", 1))

    def test_unavailable_model_falls_back(self):
        rows, report = self.run_agent(llm.LLMUnavailable("down"))
        self.assertEqual((report["x.png"]["status"], rows["x.png"]), ("unavailable", self.hand["x.png"]))


class ImageClient(FakeClient):
    """A client with chat_image (like ClaudeCodeClient): the vision agent must use it."""

    def chat_image(self, system, image_path, purpose, max_tokens=4000):
        self.prompts.append(("image", Path(image_path).name))
        return self.chat([], purpose)


class VisionImageClientTest(unittest.TestCase):
    def test_chat_image_is_used_when_available(self):
        fake = ImageClient([json.dumps({"rows": [dict(ROW)]})])
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "x.png"
            img.write_bytes(b"\x89PNG fake")
            rows, report = vision_agent.read_images({"x.png": img}, {"x.png": [dict(ROW)]},
                                                    ({"a@example.com"}, set(), {"user_7"}), fake)
        self.assertEqual(fake.prompts[0], ("image", "x.png"))
        self.assertEqual(report["x.png"]["status"], "agree")


class ClaudeCacheTest(unittest.TestCase):
    def test_image_answer_is_cached_by_image_content(self):
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "x.png"
            img.write_bytes(b"\x89PNG one")
            c = llm.ClaudeCodeClient(offline=True, cache_dir=d)
            key = c._image_key("SYS", img, 100)
            Path(d, f"{key}.json").write_text(json.dumps({"model": "m", "usage": {}, "answer": "R"}))
            self.assertEqual(c.chat_image("SYS", img, "vision:x", max_tokens=100), "R")
            img.write_bytes(b"\x89PNG two")            # different content -> different key
            with self.assertRaises(llm.LLMUnavailable):
                c.chat_image("SYS", img, "vision:x", max_tokens=100)


class CacheTest(unittest.TestCase):
    def test_cached_answer_needs_no_key(self):
        with tempfile.TemporaryDirectory() as d:
            c = llm.Client(offline=True, cache_dir=d)
            msgs = [{"role": "user", "content": "hi"}]
            key = c._key(msgs, {"temperature": 0, "max_tokens": 10})
            Path(d, f"{key}.json").write_text(json.dumps(
                {"model": "m", "usage": {"prompt_tokens": 3, "completion_tokens": 1}, "answer": "OK"}))
            self.assertEqual(c.chat(msgs, "test", max_tokens=10), "OK")
            self.assertEqual(c.usage["cached_calls"], 1)
            with self.assertRaises(llm.LLMUnavailable):
                c.chat([{"role": "user", "content": "other"}], "test", max_tokens=10)

    def test_extract_json(self):
        self.assertEqual(llm.extract_json('```json\n[{"id": 1}]\n```'), [{"id": 1}])
        self.assertEqual(llm.extract_json('Sure: {"rows": []} done'), {"rows": []})


if __name__ == "__main__":
    unittest.main(verbosity=1)
