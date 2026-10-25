# FINAL VALIDATION FINDINGS (session 13, 2026-10-25 17:33–17:40 IST)

## 1. The regression: what an empty snapshot proves

### Timelines (from raw evidence)

**case_24** (gold, held-out). requested 09-01 12:00, reported 09-02 12:00, audit_at 09-15 12:00.
- 09-15 09:41: evidence_92 `service_resource_export` (file 11:44:55). The `profile_lookups` row for account_5334 has
  status_code 200 and a profile carrying the subject's email: **record-specific, present**.
- 09-15 12:00: evidence_51 `customer_data_snapshot_bundle` (records_assurance_service). `customer_profiles` is
  `[]`; the bundle's other collections hold only tombstone_440, tombstone_9178, audit_record_6909 and
  audit_record_7068. These are gold records of case_31 and case_32, not of case_24's subject. **The bundle never
  mentions case_24's subject.**
- Gold: REPORT_REMAINING_RECORD account_5334 cited to evidence_92 → the account is PRESENT at audit_at.

**case_31** (gold). Subject mentioned in evidence_51 (its tombstone and audit record are there). account_4857 has no
observation of its own; it appears only in one DELETE_RECORD activity row. Gold: VERIFY_RECORD_ABSENT cited to
**evidence_51**.

**case_01, case_02, case_04** (gold). Each account is never observed. Gold: VERIFY_RECORD_ABSENT cited to evidence_54,
a **SQL dump** (failover replica + primary `customer_profiles` tables) that does not mention these subjects at all.

**Own case (b)**. evidence_b1 (05-01 bundle) shows account_9001 with Ada's email (present). evidence_b2 (06-01
bundle) has `customer_profiles: []` and holds only decoy records (look-alike email and hash). It never mentions Ada.
audit_at 06-15.

### Answers
1. *Empty snapshot, never-observed record:* a SQL table dump proves absence for any subject (3/3 gold). A JSON
   assurance bundle proves absence only for subjects it mentions (1/1 gold, case_31). No gold case uses a bundle for
   an unmentioned subject.
2. *Empty snapshot, record observed individually before:* a bundle that does not mention the subject proves nothing
   about it (case_24: gold keeps the record PRESENT).
3. *Can a later exhaustive snapshot override a record-specific observation?* Yes for a SQL dump: it is a
   point-in-time copy of the whole table, and a missing row means the record is gone. The replica-drift exception
   (a replica still holding the row) is kept. No gold case contradicts this; the files' structure supports it
   (inventories carry `snapshot_scope` naming the systems covered).
4. *Evidence required for absence of a previously observed record:* a record-specific negative (404 / rows=0 /
   NOT_FOUND), or a later exhaustive table dump of its system without the row, or a later bundle that covers the
   subject and lacks the record.

### Which was wrong
- **The v4 implementation ("coverage only if unobserved") was too broad.** It explains gold, but it lets a stale
  observation beat an exhaustive SQL dump. On the 518 it changed case_33 (screenshot 06-18 vs inventory 07-03) and
  case_34 in the wrong direction.
- **The own case (b) expectation (session 3) was also wrong.** It treated a bundle that mentions only decoys as
  proof that Ada's account is gone, which contradicts case_24.
- **Fix:** `scoped_bundles=True` (JSON bundles prove absence only for mentioned subjects; SQL dumps are exhaustive;
  the latest evidence wins). `coverage_only_if_unobserved` is off by default and kept as a measured option. Tests:
  `test_json_bundle_proves_absence_only_for_subjects_it_covers` and
  `test_sql_dump_is_exhaustive_and_overrides_an_earlier_observation` (both failed first).
- **Ambiguity left:** gold cannot separate the two rules. No gold case has an exhaustive dump after an observation,
  or a bundle-only proof for an unmentioned subject. The choice rests on the file semantics above, not on a score.

### Own case (b): old and new expectation
- **Old (session 3):** COMPLETE, `VERIFY_RECORD_ABSENT account_service/account_9001 evidence_b2`. Reasoning: "the
  latest evidence ≤ audit_at is evidence_b2, a covering snapshot of account_service without the row."
- **New:** INCOMPLETE:
  - `REPORT_REMAINING_RECORD account_9001 evidence_b1`;
  - `DELETE_RECORD` (empty evidence);
  - `VERIFY_RECORD_ABSENT` (empty evidence).

  Reasoning: evidence_b2 mentions only decoys, so like evidence_51 in case_24 it proves nothing about Ada. The
  decoy assertions are unchanged.
- The change is in `make_fixtures.py`, `expected_output.csv` and CASE.md (which keeps the old text). No other
  fixture changed.

## 2. Baseline (final_version_4) re-verified, with definitions

`score.py`:
- **exact** = cases whose status and full steps array are equal / cases;
- **step P/R/F1** = pooled multiset matches over the split's steps (tp / predicted steps, tp / gold steps);
- **sequence** = ordered (operation, system_id, resource_id) equal / cases.

| | final_version_3 | final_version_4 |
|---|---|---|
| dev exact | 15/22 = 0.682 | 17/22 = 0.773 |
| held-out exact | 3/10 = 0.300 | 4/10 = 0.400 |
| all-32 exact | 18/32 = 0.562 | 21/32 = 0.656 |
| dev step F1 | tp 114 / pred 115 / gold 121 = 0.966 | 115 / 115 / 121 = 0.975 |
| held-out step F1 | 63 / 63 / 72 = 0.933 | 65 / 65 / 72 = 0.949 |
| all-32 step F1 | 177 / 178 / 193 = 0.954 | 180 / 180 / 193 = 0.965 |

All reported figures reproduce. **Held-out case_24 influenced rules 3 (v4) and scoped bundles (v5); its held-out
gain is not independent validation.** The dev gains (case_17 newest account; case_08 status-free fallback) were
derived on dev.

## 3. Further search (remaining gold mismatches after v5)

Remaining differences (32 cases):
- dev: analytics missing in case_03, 04, 21; account_004 (no delete event); account_008 fixed in v4; audit records
  in case_18 and 20;
- held-out: account_410, 5482, 7012 (same-hour, same-status slots); analytics missing in case_25 to 28.

| hypothesis (stated before testing) | result | decision |
|---|---|---|
| scoped bundles change no gold case but fix the semantics | gold identical; 518: 4 rows (2 reverted to v3, 2 citations switched to SQL dumps) | **kept** |
| analytics status-match finder | 3/19 gold false picks (session 12) | rejected |
| same-status slot ordering | chance on every key (session 12) | rejected |
| account → analytics coupling | 0/73 (session 12) | rejected |
| state floor (evidence ≥ reported_at) | 34 unsupported removals (session 12) | rejected |

No further generalizable defect was found. Every remaining gold miss is a record that no participant evidence ties
to the requester (anonymized analytics, audit records with no trace, an account with no delete event), or an account
in a slot that cannot be disambiguated. No forced assignment was made in the 117 ambiguous rows.
