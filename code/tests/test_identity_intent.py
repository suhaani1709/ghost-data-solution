"""Acceptance tests for loaders, identity resolution and intent detection.

Run:  python3 code/tests/test_identity_intent.py      (summary + tests)
      python3 -m unittest discover -s code/tests -v   (tests only)
"""
import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghost import identity, intent, loaders  # noqa: E402

DATA = loaders.load_all()
INDEX = identity.IdentityIndex.from_dataset()


def resolutions(requests):
    return {row.case_id: INDEX.resolve_request(row) for row in requests.itertuples(index=False)}


def align_non_delete_with_activity(requests, labels, activity):
    """Pair each NON_DELETE case with a CLASSIFY_REQUEST "non-deletion" event.

    Activity rows carry an account_* id, not an email, and connecting the
    account to a user would take evidence parsing (not built yet). So
    the check is temporal: walk the cases by requested_at and give each the
    earliest unused classification event in [requested_at, audit_at].
    Returns (pairs, unmatched_cases, unmatched_events).
    """
    events = activity[(activity.event_type == "CLASSIFY_REQUEST")
                      & activity.details.str.contains("non-deletion")].sort_values("event_time")
    cases = requests[requests.case_id.map(labels) == intent.NON_DELETE].sort_values("requested_at")
    used, pairs, unmatched_cases = set(), [], []
    for case in cases.itertuples(index=False):
        hit = next((e for e in events.itertuples(index=False)
                    if e.activity_id not in used and case.requested_at <= e.event_time <= case.audit_at), None)
        if hit is None:
            unmatched_cases.append(case.case_id)
            continue
        used.add(hit.activity_id)
        pairs.append((case.case_id, case.requested_at, hit.activity_id, hit.event_time, hit.resource_id))
    unmatched_events = [e.activity_id for e in events.itertuples(index=False) if e.activity_id not in used]
    return pairs, unmatched_cases, unmatched_events


class LoaderTests(unittest.TestCase):
    def test_row_counts(self):
        self.assertEqual(len(DATA["requests"]), 518)
        self.assertEqual(DATA["requests"].case_id.nunique(), 518)
        self.assertEqual(len(DATA["sample_requests"]), 32)
        self.assertEqual(len(DATA["sample_output"]), 32)
        self.assertEqual(len(DATA["output_template"]), 0)

    def test_no_nan_values(self):
        for name, df in DATA.items():
            self.assertFalse(df.isna().any().any(), name)


class IdentityTests(unittest.TestCase):
    def test_snapshot_hash_is_sha256_of_email(self):
        bad = [s.user_id for s in INDEX.sets.values() if identity.email_sha256(s.email) != s.email_hash]
        self.assertEqual(bad, [])

    def test_identity_set_contains_history(self):
        for row in DATA["audit_log"].itertuples(index=False):
            ident = INDEX.sets[row.user_id]
            pool = {"email": ident.emails, "phone": ident.phones, "email_hash": ident.email_hashes}[row.field_name]
            for value in (row.old_value, row.new_value):
                norm = identity.normalize_email(value) if row.field_name == "email" else value
                self.assertIn(norm, pool, row.audit_id)
            if row.field_name == "email":
                self.assertIn(identity.email_sha256(row.old_value), ident.email_hashes)

    def test_every_request_resolves_to_exactly_one_user(self):
        res = resolutions(DATA["requests"])
        bad = {cid: r for cid, r in res.items() if r.user_id is None or len(r.candidates) != 1}
        self.assertEqual(bad, {})

    def test_historical_only_count(self):
        res = resolutions(DATA["requests"])
        self.assertEqual(Counter(r.match for r in res.values()), {"current": 418, "historical": 100})

    def test_samples_resolve(self):
        res = resolutions(DATA["sample_requests"])
        self.assertTrue(all(r.user_id for r in res.values()))

    def test_exact_matching_only(self):
        email = DATA["requests"].email.iloc[0]
        self.assertIsNotNone(INDEX.resolve_email(email.upper() + " ").user_id)
        self.assertEqual(INDEX.resolve_email(email.replace("@", "1@")).match, "none")
        self.assertEqual(INDEX.resolve_email(email.replace("l", "i", 1)).match, "none")

    def test_ambiguous_email_is_not_guessed(self):
        a, b = sorted(INDEX.sets)[:2]
        sa = INDEX.sets[a]
        sets = dict(INDEX.sets)
        sets[b] = identity.IdentitySet(**{**INDEX.sets[b].__dict__,
                                          "emails": INDEX.sets[b].emails | {sa.email}})
        r = identity.IdentityIndex(sets).resolve_email(sa.email)
        self.assertEqual((r.user_id, r.match), (None, "ambiguous"))


class IntentTests(unittest.TestCase):
    def test_counts(self):
        labels, unknown = intent.classify_requests(DATA["requests"])
        self.assertEqual(unknown, [])
        self.assertEqual(Counter(labels.values()), {intent.DELETE: 508, intent.NON_DELETE: 10})

    def test_template_coverage(self):
        self.assertEqual(sum(1 for v in intent.OPENINGS.values() if v[0] == intent.DELETE), 17)
        self.assertEqual(sum(1 for v in intent.OPENINGS.values() if v[0] == intent.NON_DELETE), 10)
        self.assertEqual({v[1] for v in intent.OPENINGS.values()}, {"en", "pt", "es", "fr", "ja", "ko"})

    def test_non_delete_aligns_with_classify_activity(self):
        labels, _ = intent.classify_requests(DATA["requests"])
        pairs, unmatched_cases, unmatched_events = align_non_delete_with_activity(
            DATA["requests"], labels, DATA["activity"])
        if unmatched_cases or unmatched_events:
            print(f"\nMISMATCH cases without event: {unmatched_cases}; events without case: {unmatched_events}")
        self.assertEqual((len(pairs), unmatched_cases, unmatched_events), (10, [], []))

    def test_no_sample_is_non_delete(self):
        labels, _ = intent.classify_requests(DATA["sample_requests"])
        self.assertNotIn(intent.NON_DELETE, labels.values())

    def test_unseen_sentence_is_unknown(self):
        opening = next(k for k, v in intent.OPENINGS.items() if v[0] == intent.DELETE)
        self.assertEqual(intent.classify(opening)[0], intent.DELETE)
        self.assertEqual(intent.classify(opening + " Actually, please keep everything.")[0], intent.UNKNOWN)
        self.assertEqual(intent.classify("Please delete my account.")[0], intent.UNKNOWN)
        self.assertEqual(intent.classify("")[0], intent.UNKNOWN)

    def test_contradicting_follow_up_is_unknown(self):
        opening = next(k for k, v in intent.OPENINGS.items() if v[0] == intent.DELETE)
        self.assertEqual(intent.classify(opening + " Do not close the account.")[0], intent.UNKNOWN)

    def test_effective_intent_defaults_unknown_to_delete_with_warning(self):
        unknown = "Please delete my account."
        self.assertEqual(intent.classify(unknown)[0], intent.UNKNOWN)
        with self.assertLogs("ghost.intent", level="WARNING") as logs:
            self.assertEqual(intent.effective_intent(unknown), intent.DELETE)
        self.assertIn("UNKNOWN", logs.output[0])
        non_delete = next(k for k, v in intent.OPENINGS.items() if v[0] == intent.NON_DELETE)
        self.assertEqual(intent.effective_intent(non_delete), intent.NON_DELETE)

    def test_effective_intent_matches_strict_on_eval_set(self):
        labels, _ = intent.classify_requests(DATA["requests"])
        for row in DATA["requests"].itertuples(index=False):
            self.assertEqual(intent.effective_intent(row.request_text), labels[row.case_id])

    def test_curly_apostrophe_normalized(self):
        text = "I’d like to download my account information in a portable format."
        self.assertEqual(intent.classify(text)[0], intent.NON_DELETE)


def print_summary():
    reqs, samples = DATA["requests"], DATA["sample_requests"]
    res = resolutions(reqs)
    labels, unknown = intent.classify_requests(reqs)
    s_labels, s_unknown = intent.classify_requests(samples)
    s_res = resolutions(samples)
    pairs, uc, ue = align_non_delete_with_activity(reqs, labels, DATA["activity"])

    def row(k, v):
        print(f"  {k:<44}{v}")

    print("=== Identity ===")
    row("users / audit rows", f"{len(INDEX.sets)} / {len(DATA['audit_log'])}")
    row("users with historical emails", sum(1 for s in INDEX.sets.values() if s.historical_emails))
    m = Counter(r.match for r in res.values())
    row("eval requests resolved (current/historical)", f"{m['current']} / {m['historical']}")
    row("eval unresolved / ambiguous", f"{m['none']} / {m['ambiguous']}")
    sm = Counter(r.match for r in s_res.values())
    row("sample requests resolved (current/historical)", f"{sm['current']} / {sm['historical']}")
    print("=== Intent (eval, 518) ===")
    c = Counter(labels.values())
    row("DELETE / NON_DELETE / UNKNOWN", f"{c[intent.DELETE]} / {c[intent.NON_DELETE]} / {c[intent.UNKNOWN]}")
    lang = Counter(intent.OPENINGS[intent.split_sentences(t)[0]][1]
                   for t, cid in zip(reqs.request_text, reqs.case_id) if labels[cid] == intent.DELETE)
    row("DELETE by language", dict(sorted(lang.items())))
    for cid, reason in unknown:
        row(f"UNKNOWN {cid}", reason)
    print("=== NON_DELETE vs CLASSIFY_REQUEST activity (temporal pairing) ===")
    for cid, req_at, aid, ev_at, res_id in pairs:
        row(f"{cid} req {req_at}", f"{aid} {ev_at} {res_id}")
    row("mismatches (cases / events)", f"{uc} / {ue}")
    print("=== Intent (samples, 32) ===")
    sc = Counter(s_labels.values())
    row("DELETE / NON_DELETE / UNKNOWN", f"{sc[intent.DELETE]} / {sc[intent.NON_DELETE]} / {sc[intent.UNKNOWN]}")
    for cid, reason in s_unknown:
        row(f"UNKNOWN {cid}", reason[:90])
    print()


if __name__ == "__main__":
    print_summary()
    unittest.main(verbosity=2)
