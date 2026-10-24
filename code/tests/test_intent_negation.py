"""Unit tests for explicit negation of deletion in intent.effective_intent.

The strict classifier is unchanged: an unseen text is UNKNOWN. An UNKNOWN
text that contains a sentence from intent.NEGATIONS (an explicit refusal of
deletion) is NON_DELETE, with a logged warning, instead of the DELETE default.
Any other UNKNOWN text keeps the DELETE default, also logged.

Run:  python3 code/tests/test_intent_negation.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghost import intent, loaders  # noqa: E402

OWN_CASE_A = "Please do not delete my account. I still use it every week."
VARIANTS = ["Please don’t delete my account.", "Do not delete my account. Thanks.",
            "I do not want my account deleted.", "Please do not close my account. It is still in use."]


class NegationTest(unittest.TestCase):
    def test_own_case_a_is_not_a_deletion(self):
        self.assertEqual(intent.classify(OWN_CASE_A)[0], intent.UNKNOWN)
        with self.assertLogs(intent.log, "WARNING") as logs:
            self.assertEqual(intent.effective_intent(OWN_CASE_A), intent.NON_DELETE)
        self.assertIn("negat", logs.output[0])

    def test_variants(self):
        for text in VARIANTS:
            with self.subTest(text=text), self.assertLogs(intent.log, "WARNING"):
                self.assertEqual(intent.effective_intent(text), intent.NON_DELETE)

    def test_negation_after_a_deletion_opening_is_not_a_deletion(self):
        text = "Please erase the account linked to this email address. Please do not delete my account."
        with self.assertLogs(intent.log, "WARNING"):
            self.assertEqual(intent.effective_intent(text), intent.NON_DELETE)

    def test_other_unknown_text_keeps_the_delete_default_and_is_logged(self):
        with self.assertLogs(intent.log, "WARNING") as logs:
            self.assertEqual(intent.effective_intent("I no longer need this account."), intent.DELETE)
        self.assertIn("defaulting to DELETE", logs.output[0])

    def test_all_518_and_32_sample_intents_unchanged(self):
        reqs = loaders.load_deletion_requests()
        labels, unknown = intent.classify_requests(reqs)
        self.assertEqual(unknown, [])
        effective = [intent.effective_intent(t, warn=False) for t in reqs.request_text]
        self.assertEqual(effective, [labels[c] for c in reqs.case_id])
        samples = loaders.load_sample_requests().request_text
        self.assertEqual({intent.effective_intent(t, warn=False) for t in samples}, {intent.DELETE})


if __name__ == "__main__":
    unittest.main(verbosity=1)
