# Own case (f): late-exported log, COMPLETE case

**Input.** The same user and the same late log as case (e) (here evidence_f3, captured after
audit_at). evidence_f1 (2026-06-20) holds `search_9401` with the user's email. evidence_f2
(2026-07-08) is a covering search_service snapshot without it.

**Late-export rule (AGENTS.md §6.2, §6.6, problem_statement.md Rules).** Use only information
available at or before audit_at, and never cite a file captured after it. The log file was
exported after audit_at, but its trace events are timestamped before audit_at, so the facts
existed at audit time. They can establish that the record belongs to the user, but the file
cannot be cited. A retained SECURITY_AUDIT_LOG record (rule RETAIN) only adds a
VERIFY_RECORD_PRESENT step. In an INCOMPLETE case, that future check carries evidence_id "",
so it needs no citation. The trace dated after audit_at (account lookup at 09:30) is ignored.

**Hand derivation (written before running the pipeline).** search_9401 is ABSENT at audit_at,
cited to evidence_f2, so it is compliant and the case is COMPLETE. In a COMPLETE case every
verification step must cite evidence captured at or before audit_at. audit_record_9402 is
evidenced only by evidence_f3, captured after audit_at, so no valid citation exists. It is
omitted rather than cited to a late file or given an invented citation. It cannot change the
status either way, because it is retained and compliant.

**Expected:** COMPLETE: VERIFY_RECORD_ABSENT search_9401 (evidence_f2).
