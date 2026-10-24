"""Cue fallback for request texts the sentence tables do not cover.

Run:  python3 -m unittest code/tests/test_intent_fallback.py -v
The synthetic texts below are new wording, not dataset sentences.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghost import intent, loaders  # noqa: E402

REFUSALS = [
    "Please do not delete my account. I still use it every week.",
    "Don't close the account, I only want my phone number updated.",
    "I am not asking you to erase anything; I just need my invoices.",
    "Keep my account open please, but tell me what data you store.",
    "This is not a request to delete my data.",
    "Could you fix my address without removing my order history?",
    "Por favor, no eliminen mi cuenta.",
    "Por favor, não excluam a minha conta.",
    "Merci de ne pas supprimer mon compte.",
    "アカウントは削除しないでください。",
    "제 계정을 삭제하지 마세요.",
]
OTHER_REQUESTS = [
    "Please unsubscribe me from the newsletter.",
    "Please remove me from marketing emails only.",
    "My billing address is out of date.",
    "I'd like a copy of my order history.",
    "I can't access my profile after the app update.",
]
DELETIONS = [
    "Hello, please get rid of everything you hold on me and delete the account.",
    "Kindly erase my profile and every copy of my personal data.",
    "I was told my data was deleted, but I don't think it was deleted. Please finish it.",
    "Forget me: close the account and remove my details from search.",
    "Quiero que eliminen mi cuenta y mis datos personales.",
    "Je souhaite la suppression de mon compte.",
    "Please delete my account without delay.",
    "Why is the account still active after my request?",       # no cue: deletion-intake default
]


class FallbackTest(unittest.TestCase):
    def test_unseen_refusals_fail_closed(self):
        for text in REFUSALS:
            with self.subTest(text=text):
                self.assertEqual(intent.classify(text)[0], intent.UNKNOWN)
                self.assertEqual(intent.effective_intent(text), intent.NON_DELETE)

    def test_unseen_other_requests_are_not_deletions(self):
        for text in OTHER_REQUESTS:
            with self.subTest(text=text):
                self.assertEqual(intent.effective_intent(text), intent.NON_DELETE)

    def test_unseen_deletions_stay_deletions(self):
        for text in DELETIONS:
            with self.subTest(text=text):
                self.assertEqual(intent.effective_intent(text), intent.DELETE)

    def test_table_match_is_final(self):
        text = "Please erase the account linked to this email address."
        self.assertEqual(intent.classify(text)[0], intent.DELETE)
        self.assertEqual(intent.effective_intent(text), intent.DELETE)


@unittest.skipUnless((loaders.DATASET_DIR / "deletion_requests.csv").is_file(), "dataset/ absent")
class DatasetConsistencyTest(unittest.TestCase):
    def test_every_sample_text_is_a_deletion(self):
        for r in loaders.load_sample_requests().itertuples():
            self.assertEqual(intent.effective_intent(r.request_text), intent.DELETE, r.case_id)

    def test_fallback_agrees_with_tables_on_every_evaluation_text(self):
        # The fallback is never used for these (the tables cover them); as an independent
        # classifier it must reproduce every hand label, including the 10 non-deletions.
        for r in loaders.load_deletion_requests().itertuples():
            label = intent.classify(r.request_text)[0]
            self.assertEqual(intent.infer_unknown(r.request_text)[0], label, r.case_id)


if __name__ == "__main__":
    unittest.main()
