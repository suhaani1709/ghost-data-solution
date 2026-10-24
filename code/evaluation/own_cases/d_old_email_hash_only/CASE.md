# Own case (d): old email whose resource appears only under its SHA-256

**Input.** A deletion request from `dev.m.old@example.com`. That email is not in `user_identities.csv`.
audit_d1 (2026-02-01) shows user_9201 changed email from it to `dev.marlow@example.org`. evidence_d1
(log, 2026-07-01) has an `index_query_completed` hit on `search_9301` whose `correlation_key`
is SHA-256(`dev.m.old@example.com`) = `983527d5e2176e287568d1ac46dff4a32ce4201d8ed6a049e9bf55f03bf0ff9a`. The plain old email appears nowhere in the evidence.
`account_9302` returns 404 in the same log, but nothing ties it to the user.

**Hand derivation (written before running the pipeline).**
§6.5: resolve current and historical identifiers; the request email may be historical, so
it resolves to user_9201. §6.6: match through hashes too. The SHA-256 of the historical
email is a user token, so search_9301 is the user's search entry (SEARCH_INDEX_ENTRY,
rule_03 DELETE). An index hit on 2026-07-01, before audit_at, means the entry is PRESENT.
account_9302 is not linked to any user token, so it is not reported.

**Expected:** INCOMPLETE,
1 FINDING REPORT_REMAINING_RECORD search_service/search_9301 PRESENT evidence_d1;
2 REMEDIATION DELETE_RECORD ... ABSENT "";
3 VERIFICATION VERIFY_RECORD_ABSENT ... ABSENT "".
