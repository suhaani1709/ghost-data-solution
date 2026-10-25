# Own case (b): look-alike decoy identifiers must not link

**Input.** A deletion request from `ada.quill@example.com` (user_9001), audit_at 2026-06-15.
- evidence_b1 (2026-05-01): `account_9001` holds the user's email, so it is the user's profile.
- evidence_b2 (2026-06-01): the `account_service` / `customer_profiles` snapshot is empty.
  The same bundle holds two decoys: `search_9002` with display name "Ada Quill" and the
  look-alike email `ada.quill@exarnple.com` ("rn" in place of "m"), and `analytics_9003` whose
  `email_hash` is SHA-256 of the look-alike `ada.quil@example.com`. Neither is a token of user_9001.

**Hand derivation (written before running the pipeline).**
AGENTS.md §6.6: match evidence through exact identifiers. A look-alike email or the hash of
one is not the user's identifier, and a shared display name alone is not a grounded link.
The only relevant resource is `account_9001` (USER_PROFILE, rule_01 DELETE). The latest
evidence on or before audit_at is evidence_b2, a covering snapshot of account_service
without the row, so the record is ABSENT. That is compliant, and the case is COMPLETE
with one verification step citing evidence_b2.

**Expected:** COMPLETE,
`[{1, VERIFICATION, account_service, account_9001, VERIFY_RECORD_ABSENT, ABSENT, evidence_b2}]`.
A row for search_9002 or analytics_9003 would be a decoy false positive.

## Correction (2026-10-25, session 13) — the original expectation above was wrong

**Original expectation (session 3, kept for the record):** COMPLETE, one VERIFY_RECORD_ABSENT for account_9001 cited to
evidence_b2, on the assumption that an empty `customer_profiles` collection in a later snapshot bundle proves that
every account is gone.

**Contradiction found in the real data and the answer key:**
- The dataset's `customer_data_snapshot_bundle_*.json` files are records-assurance bundles that hold only a few
  subjects' records. evidence_51 holds just 2 tombstones and 2 audit records, the records of two specific requests.
- Gold case_24: account_5334 was observed present (evidence_92, 09:41). The evidence_51 bundle at 12:00 has an empty
  `customer_profiles` collection and does not mention that subject. Gold still reports the account PRESENT
  (REPORT_REMAINING_RECORD citing evidence_92).
- Gold case_31: the same bundle *does* mention its subject, and gold uses it to prove that subject's
  never-observed account absent.
- Gold cites SQL table dumps as absence proof for subjects the dump never mentions (case_01, case_02, case_04):
  a table dump is exhaustive, a bundle is not.

**Corrected expectation:** evidence_b2 mentions only the decoys, never Ada. Its empty collection says nothing about
Ada's account, so account_9001 is still PRESENT at audit_at by its own evidence (evidence_b1).
Expected: INCOMPLETE:
1 REPORT_REMAINING_RECORD account_service/account_9001 (evidence_b1);
2 DELETE_RECORD (empty evidence);
3 VERIFY_RECORD_ABSENT (empty evidence).

The case's purpose is unchanged: search_9002 and analytics_9003, the look-alike decoys, must not appear.
