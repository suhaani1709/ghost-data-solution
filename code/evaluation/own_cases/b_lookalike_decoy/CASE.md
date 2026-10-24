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
