# Own case (c): primary deleted, failover replica still holds the row

**Input.** A deletion request from `cora.vance@example.com` (user_9101). reported_status is
COMPLETE, and activity_c1 claims DELETE_RECORD SUCCESS on `account_9101` (2026-06-18).
evidence_c1 (SQL, 2026-06-20) has `customer_profiles_primary` without account_9101, but
`customer_profiles_failover_replica` still holds account_9101 with the user's name, email and phone.

**Hand derivation (written before running the pipeline).**
Reported statuses and activity results are claims (§6.6). README: SQL captures can hold
replicas "so replication drift can be investigated directly". A copy of the profile still
exists in the failover replica, so the USER_PROFILE (rule_01 DELETE) record is PRESENT, cited
to evidence_c1. With no data flow or backup in evidence, the plan is: finding, delete, and
verify absent. Remediation and future verification use `""`.

**Expected:** INCOMPLETE,
1 FINDING REPORT_REMAINING_RECORD account_service/account_9101 PRESENT evidence_c1;
2 REMEDIATION DELETE_RECORD ... ABSENT "";
3 VERIFICATION VERIFY_RECORD_ABSENT ... ABSENT "".
