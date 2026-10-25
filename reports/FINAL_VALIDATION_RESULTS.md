# FINAL VALIDATION RESULTS (session 13)

Candidate: `~/Desktop/final_version_5/`. Previous candidates are untouched (final_version, _2, _3, _4, safe_version).

## Metrics (32 gold cases; local, not a hidden-grader score)

| metric | v3 dev | v4 dev | **v5 dev** | v3 held | v4 held | **v5 held** | v3 all | v4 all | **v5 all** |
|---|---|---|---|---|---|---|---|---|---|
| status | 22/22 | 22/22 | **22/22** | 10/10 | 10/10 | **10/10** | 32/32 | 32/32 | **32/32** |
| exact | 15/22 | 17/22 | **17/22** | 3/10 | 4/10 | **4/10** | 18/32 | 21/32 | **21/32** |
| sequence | 15/22 | 17/22 | **17/22** | 3/10 | 4/10 | **4/10** | 18/32 | 21/32 | **21/32** |
| step precision | 0.991 | 1.000 | **1.000** | 1.000 | 1.000 | **1.000** | 0.994 | 1.000 | **1.000** |
| step recall | 0.942 | 0.950 | **0.950** | 0.875 | 0.903 | **0.903** | 0.917 | 0.933 | **0.933** |
| step F1 | 0.966 | 0.975 | **0.975** | 0.933 | 0.949 | **0.949** | 0.954 | 0.965 | **0.965** |
| linkage precision | 0.983 | 1.000 | **1.000** | 1.000 | 1.000 | **1.000** | | | |

v5 equals v4 on gold. The difference between them is semantic and shows only in the 518 rows.

## Exact row changes: final_version_5 vs final_version_4

| row | field change | evidence-based reason |
|---|---|---|
| case_33 | INCOMPLETE → COMPLETE. export_1260: the REPORT_REMAINING_RECORD (evidence_23) and DELETE_RECORD steps are removed, and its VERIFY_RECORD_ABSENT now cites evidence_81. account_2373 and search_2352 verifications cite evidence_81. The audit_record_8486 future check is removed (a COMPLETE row cannot hold uncited checks) | SQL inventory evidence_81 (07-03, snapshot_scope covers the systems) lacks export_1260, after the 06-18 screenshot. The exhaustive dump proves deletion before audit_at (07-19) |
| case_34 | support_9538: the REPORT_REMAINING_RECORD (evidence_01) and DELETE_RECORD steps are removed; status stays INCOMPLETE | a later exhaustive SQL inventory of support_platform lacks support_9538 |
| case_308 | account_8647 VERIFY_RECORD_ABSENT: evidence_31 → evidence_72 | evidence_31 is a bundle that never mentions this subject; evidence_72 is the SQL inventory (05-04) that proves absence |
| case_309 | account_4319 VERIFY_RECORD_ABSENT: evidence_31 → evidence_72 | same |

case_33 and case_34 are exactly as in final_version_3. Relative to v3, v5 changes only the two citations
(case_308, case_309). Status counts: COMPLETE 152, INCOMPLETE 356, NOT_APPLICABLE 10 (same as v3).

## Regression and verification

| check | result |
|---|---|
| `python3 -m unittest discover -s code/tests` (repo) | 156 run, OK, 0 skipped |
| `python3 code/evaluation/run_own_cases.py` | **4/4** (own case b expectation corrected; see findings) |
| `python3 code/evaluation/validate.py output.csv` | VALID, 0 invalid rows; 1 warning (case_63: a zero-link COMPLETE []; nothing can be cited) |
| `python3 code/evaluation/score.py` | table above |
| `python3 code/evaluation/account_backtest.py` | status variant 1.000 / 0.730 tune, 1.000 / 0.735 held (the script's fixed variants; status_windows=1 measured at tune 0.746 in session 12) |
| `python3 code/evaluation/audit_rows.py` | invariants a, b, c hold on gold; 518: 117 rows without an account; 0 structure errors; citation = latest mentioning file 1050/1050 |
| determinism | two offline runs byte-identical |
| clean extraction of final_version_5/code.zip (`env -i PATH=/usr/bin:/bin`, no claude, no keys, dataset symlinked) | default, `--offline`, `--no-llm` and a second run are byte-identical to the candidate output.csv; `--sample` gives 32 rows; validator exit 0; 156 tests OK (4 skipped); compileall OK; bad dataset path exits 1 |
| skipped tests in the extraction | 3 need `pdftotext` (not on the minimal PATH; the committed text fallback is tested separately); 1 compares the planner table with `problem_statement.md`, which is not in the zip |
| archive | 99 files; 0 cache, 0 forbidden entries, 0 secrets, 0 case-id lists |
| schema / order | header `case_id,deletion_status,steps_json`; 518 rows; numeric request order; LF only |

## Hashes

| artifact | size (B) | SHA-256 |
|---|---|---|
| final_version_5/output.csv | 609,237 | 576612280e681c676b09c0ef4b753085ef7055599f592f1cd625f0cf6f3e0b26 |
| final_version_5/code.zip | 200,866 | a6d2018b72e939ca632c94b809682d9e22b4f5154333f2ac7e3711070721b925 |
| final_version_4/output.csv | 610,171 | 2b8bcc20de96a1bc6e5f828133b587af022ecf22ec5d263fb30d53c22d985a66 |
| final_version_4/code.zip | 197,295 | c75c864885dcae21b1d411064083d960ee21ca714549abdfa5514bbcab95d9fb |

## Recommendation

**Submit final_version_5.** On the 32 gold cases it is identical to v4: 21/32 exact, step F1 0.965, precision 1.000.
- It fixes the semantic error in v4's snapshot rule. The two v4 row changes, case_33 and case_34, let a stale
  observation override an exhaustive SQL dump; v5 restores them.
- It cites an exhaustive dump instead of a non-covering bundle in two rows, which matches gold's citation pattern
  (3/3 and 1/1).
- Own cases pass 4/4.

**Remaining uncertainty:**
- Gold has no case with an exhaustive dump after an observation, so the case_33 and case_34 direction rests on file
  semantics, not on a measured score.
- Held-out case_24 shaped the rule.
- No hidden-grader improvement is claimed.
