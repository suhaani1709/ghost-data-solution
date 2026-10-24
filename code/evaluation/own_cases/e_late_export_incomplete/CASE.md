# Own case (e): late-exported log, INCOMPLETE case

**Input.** A deletion request from `eve.tran@example.com` (user_9301), audit_at 2026-07-10T09:00.
evidence_e1 (captured 2026-07-08) still holds `search_9401` with the user's email.
evidence_e2 is a log captured 2026-07-12, after audit_at. Trace tr-9402 (08:50, before
audit_at) queries `subject_ref=user_9301` and reads `audit_record_9402` (rows=1). Trace tr-9403
(09:30, after audit_at) looks up the user's email, and `account_9403` returns 404.

**Late-export rule (AGENTS.md §6.2, §6.6, problem_statement.md Rules).** Use only information
available at or before audit_at, and never cite a file captured after it. The log file was
exported after audit_at, but its trace events are timestamped before audit_at, so the facts
existed at audit time. They can establish that the record belongs to the user, but the file
cannot be cited. A retained SECURITY_AUDIT_LOG record (rule RETAIN) only adds a
VERIFY_RECORD_PRESENT step. In an INCOMPLETE case, that future check carries evidence_id "",
so it needs no citation. The trace dated after audit_at (account lookup at 09:30) is ignored.

**Hand derivation (written before running the pipeline).** search_9401 is a SEARCH_INDEX_ENTRY
(rule_03 DELETE), PRESENT and cited to evidence_e1, so the case is INCOMPLETE. audit_record_9402
is the user's retained security record, so it gets VERIFY_RECORD_PRESENT with "". account_9403
is known only from an event after audit_at and is not reported.

**Expected:** INCOMPLETE: REPORT_REMAINING_RECORD search_9401 (evidence_e1); DELETE_RECORD
search_9401; VERIFY_RECORD_ABSENT search_9401; VERIFY_RECORD_PRESENT audit_record_9402 ("").
