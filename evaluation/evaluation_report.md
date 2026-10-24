# Evaluation report: Ghost Data Still Exists deletion-audit agent

Every number below comes from running the scripts named next to it on the final code
(including the session-4/5 account finder and the session-5 negation fix, see section 9) on 2026-10-25. Nothing is estimated.
Where a number is plain arithmetic on measured counts (for example a ceiling), the arithmetic is shown.

Reproduce:

```bash
python3 code/evaluation/score.py              # sections 1-3
python3 code/evaluation/compare.py base follow_refs images follow+images replica_any replica_drift drift+actcat account table_cover account+cover
python3 code/evaluation/breakdown.py          # section 6
python3 code/evaluation/channels.py           # section 7
python3 code/evaluation/run_own_cases.py      # section 5
python3 code/evaluation/validate.py output.csv
```

**Splits.** The 32 public samples (`dataset/sample_output.csv`) are the only labelled data.
`score.py` sorts them by `case_id`: the first 22 are **dev** and the last 10 are **held-out**.
Held-out cases were looked at only in aggregate. They were not entirely untouched, though. Held-out aggregates
were also used as a no-regression gate for kept changes ("revert any change that lowers a dev or held-out
metric", sessions 2 and 5). The one-account-per-case premise of the account finder counts accounts in all 32
sample answers. No change was rejected because of held-out, since held-out never decreased in any config
(section 9). Section 4 says which rules came from dev.

**Metric definitions** (`code/evaluation/score.py`):
- *status accuracy*: `deletion_status` equal to the gold status.
- *exact*: status and the full `steps_json` array equal.
- *step P/R/F1*: each step is the tuple (phase, system_id, resource_id, operation, state, evidence_id),
  and steps are compared as multisets, ignoring `step_no`.
- *field accuracy*: gold step *i* compared with predicted step *i* for each field. Every gold step
  counts, so a missing step lowers every field.
- *sequence accuracy*: the ordered list of (operation, system_id, resource_id) is equal.

## 1. Case-level deletion-status accuracy

| split | cases | status accuracy | exact case match |
|---|---|---|---|
| all | 32 | **1.000** (32/32) | 0.438 |
| dev | 22 | **1.000** | 0.636 |
| held-out | 10 | **1.000** | 0.000 |

Status confusion (all 32, `breakdown.py`): COMPLETE 10→10, INCOMPLETE 22→22, NOT_APPLICABLE 0
(the samples contain no non-deletion request).

## 2. Step-level and field-level accuracy

| split | step P | step R | step F1 |
|---|---|---|---|
| all | 0.994 | 0.845 | 0.913 |
| dev | 0.991 | 0.901 | 0.944 |
| held-out | 1.000 | 0.750 | 0.857 |

Field accuracy (position-aligned):

| split | step_no | phase | system_id | resource_id | operation | state | evidence_id |
|---|---|---|---|---|---|---|---|
| all | 0.84 | 0.83 | 0.64 | 0.64 | 0.66 | 0.67 | 0.84 |
| dev | 0.90 | 0.90 | 0.79 | 0.79 | 0.82 | 0.82 | 0.90 |
| held-out | 0.75 | 0.71 | 0.38 | 0.38 | 0.39 | 0.42 | 0.74 |

Precision is near 1, so emitted steps are almost always right. The loss is recall: missing
resources (section 6). Because field accuracy is position-aligned, one missing resource early in the
sort order shifts every later step. That is why held-out system/resource accuracy (0.38) is much
lower than its step recall (0.750).

## 3. Sequence accuracy

| split | sequence accuracy |
|---|---|
| all | 0.438 |
| dev | 0.636 |
| held-out | 0.000 |

The planner itself orders steps correctly. The planner oracle (`code/tests/test_planner_oracle.py`, 4/4)
rebuilds every sample answer exactly when given the gold resources. Every sequence miss therefore comes
from a missing or extra resource, not from ordering.

## 4. Which rules were derived from what

| rule / component | derived from | held-out status |
|---|---|---|
| Step sort order (phase → operation table order → system_id → resource_id) | problem_statement.md; checked on **all 32** samples | not held out |
| Treatments, including the `BACKUP_ARCHIVE` / `DATA_FLOW` overrides (DISAGREEMENTS below) | deletion_rules.csv plus **all 32** sample answers (planner oracle) | not held out |
| Intent sentence tables (17 deletion openings, 10 non-deletion, follow-ups) | reading the 518 evaluation request texts (no labels exist) | n/a |
| Reference following (one hop) | kept because **dev** precision stayed ≥ 0.95 | measured: no held-out change |
| Image evidence (`image_transcripts.md`) | hand transcript of the 11 PNGs, validated against identities | measured: no sample change |
| Replica-drift persistence (`replica_persist="drift"`) | a **dev** failure (a primary-only snapshot overrode a replica copy) | measured: no held-out change |
| Activity treatment as category fallback | **dev**: matched gold treatment for 46/46 dev resources | measured: no held-out change |
| Zero-link rule (no linked resource → COMPLETE `[]`) | problem_statement.md; the 3 **dev** zero-link cases have gold COMPLETE | measured: no held-out change |
| Account finder: one account per case; window −75/+10 min around reported_at | all 32 samples have exactly one account (count only); window from **dev** delete timings | measured: held-out +1 account, 0 wrong |
| Inventory-table coverage (SQL dump without snapshot_scope proves absence) | **dev**: gold cites such a dump as proof that a found account is absent | measured: no held-out change alone |
| Account propagation (an account belongs to one user; taken accounts leave other pools) | uniqueness of ownership; checked on **dev** (no change there) | measured: no held-out change |
| Intent negation table (UNKNOWN + explicit refusal → NON_DELETE) | own case (a) and its phrasing variants; no sample or 518 text affected | n/a |

Before session 4, none of the dev-derived rules changed a held-out metric. The account finder adds one
correct held-out account (R 0.736 → 0.750). The held-out score is otherwise the baseline linker's score. It is the closest thing we have to an
out-of-sample number for linking, but it is not strictly untouched: held-out aggregates served as a
no-regression gate, and the one-account premise counts all 32 samples. It is not out-of-sample for
planner conventions either, because every sample informed them.

## 5. Own evaluation cases (4 cases, built by us)

Each case is a directory under `code/evaluation/own_cases/<name>/` with its own `dataset/` in the
real schema (fictional people, `example.com` / `example.org` addresses, `+1 555 01xx` phones),
an `expected_output.csv`, and a `CASE.md` with the derivation. **The expected answer was derived by hand
from the rules and written down before the pipeline was run on the case.** `dataset/` was not edited.
`make_fixtures.py` regenerates the files. Run: `python3 code/evaluation/run_own_cases.py`.

| case | what it tests | expected (hand-derived) | pipeline | result |
|---|---|---|---|---|
| a_do_not_delete | "Please do not delete my account. I still use it every week." with a live profile row in evidence | `NOT_APPLICABLE`, `[]` | before session 5: `INCOMPLETE`, 3 steps (report / delete / verify account_9001). Now: `NOT_APPLICABLE`, `[]` | **FAIL → PASS** (session 5) |
| b_lookalike_decoy | the real profile is deleted (empty covering snapshot); same-name search doc with `ada.quill@exarnple.com`; analytics row with SHA-256 of `ada.quil@example.com` | `COMPLETE`, 1 step: VERIFY_RECORD_ABSENT account_9001 cited to evidence_b2 | identical | **PASS** |
| c_replica_holds_row | primary table lacks the row, failover replica table holds it; activity claims DELETE SUCCESS | `INCOMPLETE`: REPORT_REMAINING_RECORD (evidence_c1) → DELETE_RECORD → VERIFY_RECORD_ABSENT | identical | **PASS** |
| d_old_email_hash_only | request uses a historical email (audit log); the only evidence is a search hit whose `correlation_key` is SHA-256 of that old email | `INCOMPLETE`: REPORT_REMAINING_RECORD search_9301 (evidence_d1) → DELETE_RECORD → VERIFY_RECORD_ABSENT | identical | **PASS** |

**4 of 4 pass** (3 of 4 before the session-5 negation fix).

**Finding from case (a), fixed in session 5** (see section 9). The original finding: The intent classifier accepts a text only if every sentence is in
its tables. "Please do not delete my account." is not in them, so the text is `UNKNOWN`, and
`intent.effective_intent` maps `UNKNOWN` to `DELETE`, logging the warning
`intent UNKNOWN, defaulting to DELETE`. The refusal is then audited as a deletion. This default was chosen because all 518
evaluation texts are covered by the tables (0 UNKNOWN), and all 32 samples are deletions even though 23
distinct sample openings are not in the tables (score.py prints a warning for each). On the
evaluation set the default changes nothing. On unseen text it fails open toward deletion, which is
the unsafe direction for a "do not delete" request. Possible fixes, all untested: default UNKNOWN to
NOT_APPLICABLE when the text contains a negated deletion verb, or route UNKNOWN texts to review.
Either one would need re-measuring on the 23 unknown sample openings, which are all deletions.

**Fix (session 5):** `intent.NEGATIONS` is a table of explicit refusals: the case (a) phrasing, its
variants, and the refusals among the non-deletion follow-ups. The strict classifier is unchanged. An UNKNOWN
text containing a refusal is NON_DELETE (logged), and any other UNKNOWN text keeps the DELETE default
(logged). Measured: all 518 intents unchanged (508 DELETE / 10 NON_DELETE, 0 UNKNOWN), all 32 sample intents
unchanged (all DELETE), and own case (a) now passes. Tests: `code/tests/test_intent_negation.py`.

## 6. Failure analysis

**Linking is the bottleneck** (`breakdown.py`, `channels.py`):

| split | gold resources | linked gold | linkage recall | linkage precision | gold only in activity rows | ceiling for evidence linking |
|---|---|---|---|---|---|---|
| dev | 65 | 53 | 0.815 | 0.981 (53/54) | 13 (5 now found by the account finder) | (65−13)/65 = 0.800 for exact linking alone |
| held-out | 46 | 30 | 0.652 | 1.000 (30/30) | 9 (1 now found) | (46−9)/46 = 0.804 for exact linking alone |

Dev failure types now (`breakdown.py`): 8 × gold resource not in any parsed text evidence dated ≤ audit_at,
4 × in evidence but no identifier match, 1 × extra resource linked. Before the account finder: 13, 4, 1.
Of the 8 remaining dev misses, 5 are accounts where the finder abstained (several survivors), 3 are
security audit records, and 2 of those 3 have no trace in any evidence or activity row.

Why there is a recall ceiling:
1. **Activity rows have no person column.** `system_activity.csv` has 8 columns (`activity_id,
   event_time, event_type, source_system, target_system, resource_id, reported_result, details`). Except
   for the 12 `LINK_RESOURCE_IDENTITY` rows, `details` carries only resource ids. A gold resource that
   appears only in activity rows (13 dev, 9 held-out) cannot be tied to the requester by an exact
   identifier. The only links left are time windows, id numbers or names, and section 7 shows each of
   those is far too imprecise as a general channel. The account finder (section 9) narrows the
   time window to one system, one operation and one record per case, and removes tied accounts, which
   brings it to dev precision 1.000.
2. **Nulled identifiers.** The 4 dev resources that are in evidence but unmatched are compliant
   records: 3 ANONYMIZED and 1 ABSENT. Their observations dated ≤ audit_at carry **0** identifier
   tokens. The deletion workflow removed exactly the
   tokens we would link on. One such resource was recovered by reference following: it is named as
   `source_resource_id` inside a linked record. The rest have no exact link left.

Other known failures:
- Case (a) above: intent failed open on unseen text. Fixed in session 5 for explicit refusals; other unseen
  text still defaults to DELETE.
- **Zero-link rows:** 2 of the 518 output rows are COMPLETE with `[]` (zero-link rule). problem_statement.md
  allows them, so `validate.py` now reports them as a warning, not an error. They are COMPLETE because
  no evidence shows a remaining copy. The gold answer may still list verification steps we cannot cite.
  The 3 dev zero-link cases have gold COMPLETE with 1, 1 and 2 steps. That is a recall loss we accept,
  because we will not invent unevidenced steps.

## 7. Tried and rejected (measured, `channels.py`)

Each channel was added on top of the pipeline's linked set. *newG* = gold resources newly linked.
*extra* = non-gold resources added. Channel precision = newG / (newG + extra).

| channel | dev newG | dev extra | dev channel precision | dev linkage recall → | dev linkage precision → | held-out channel precision |
|---|---|---|---|---|---|---|
| A: any activity row in [requested_at, audit_at] (time window) | 13 | 6958 | 0.002 | 0.938 | 0.009 | 0.004 |
| C: A restricted to deletion_worker rows (time window) | 13 | 2744 | 0.005 | 0.938 | 0.022 | 0.009 |
| D: resource-number convention (suffix == user number) | 5 | 19 | 0.208 | 0.815 | 0.726 | 0.000 (0 new, 7 extra) |
| B: LINK_RESOURCE_IDENTITY rows naming a user token | 0 | 2 | 0.000 | 0.738 | 0.941 | — (0 new, 0 extra) |
| N: name channel (user's full name in a unit's snippet) | 0 | 2 | 0.000 | 0.738 | 0.941 | — (0 new, 0 extra) |

All five were rejected. The bar was dev precision ≥ 0.95, and the best channel (D) reaches 0.208.
For the time-window channels, 556 of A's and C's dev extras are other dev cases' gold resources,
so the windows mix different people's deletions. The name channel was measured this session as a
diagnostic only. The linker never uses names: a name appears inside records that belong to other
people (case (b) shows the same name on a decoy).

Also rejected:
- **Same-batch idea for analytics** (session 4, the account finder run with analytics_platform /
  ANONYMIZE_RECORD, only where no analytics record was linked). Unlike accounts, analytics is not one per
  case (13 gold in 32 cases). Window −75/+10 min around reported_at: dev 2 recovered, 3 wrong,
  **precision 0.400**; held-out 0 recovered, 1 wrong. Window −30/0: same numbers. Anchored on the
  account's own delete, ±10 min: dev 0 picks; ±30 min: dev 0 recovered, 1 wrong. Rejected.
- **Forced account pick** (session 5, measured only, not enabled). For cases still ambiguous after
  propagation (≥ 2 candidates), pick the delete closest to reported_at, with the user number as tie-break.
  The dev gold account is among the candidates in 5/5 such cases, but the top pick is right in only 2.
  By minimum margin between the first and second candidate: ≥0 min dev 2/3 (0.400), held 2/6, 287 rows of
  the 518; ≥2 min 2/2 (0.500), 279 rows; ≥5 min 2/2 (0.500), 260 rows; ≥10 min 2/2 (0.500), held 1/1, 169 rows;
  ≥20 min 1/2 (0.333), 32 rows; ≥30 min no dev case, 11 rows. Never near 0.95, so it stays off.
- **Same-batch idea for security audit records:** not possible. The deletion worker never acts on
  security_service (no activity row targets it), consistent with rule_12 RETAIN.
- **Account finder with a strictly-before window (−75/0):** dev 2 recovered, 0 wrong, 9 abstained.
  The gold delete is up to 8 min *after* reported_at in two dev cases, so −75/+10 was kept (5 recovered, 0 wrong).
- **Resource-number fallback for zero-link cases only:** removed. It added a wrong resource on dev,
  and dev step precision dropped (exact numbers are in log.txt, from an earlier session; not re-measured here).
- **`replica_persist="any"`:** it scores the same as `"drift"` on every metric (section 9). We kept the stricter
  `"drift"`, which also requires the same file's primary copy to lack the row.

## 8. Planner DISAGREEMENTS (verbatim from `code/ghost/planner.py`)

1. BACKUP_ARCHIVE: rule_14 says RETAIN (which elsewhere verifies VERIFY_RECORD_PRESENT), but samples verify VERIFY_RESTORE_BLOCKED and report REPORT_RESTORE_RISK -> following the samples.
2. DATA_FLOW: no data_category in deletion_rules.csv covers sync/import flows, but samples treat integration_service data_flow_* as DISABLE/VERIFY_DATA_FLOW_DISABLED -> pseudo-category from samples.
3. Category is not a function of system: support_platform is SUPPORT_MESSAGE (REDACT) or SUPPORT_ATTACHMENT (DELETE); analytics_platform is ANALYTICS_PROFILE (ANONYMIZE) or MARKETING_PROFILE (DELETE). The linker must supply the category per record.
4. No sample covers SECONDARY_IDENTIFIER, CACHE_ENTRY, PRODUCT_TELEMETRY, EMAIL_DELIVERY_LOG, LEGAL_HOLD_RECORD: their treatment comes from deletion_rules.csv alone (untested).
5. Rule conditions (e.g. rule_05 'shared context must be retained', rule_12 'within retention period') are not evaluated here; the caller must pick the category whose condition holds.

## 9. What improved at each step

**Per commit.** Each commit's `code/` was re-run on the samples and on the 518 cases with this session's
`validate.py`. "Empty COMPLETE" counts rows that the old validator called invalid and the current one warns about.

| commit | change | dev status | dev F1 | dev exact | held F1 | held exact | empty COMPLETE (518) | rows differing from session-3 output |
|---|---|---|---|---|---|---|---|---|
| c7f13b5 | baseline v0 | 0.955 | 0.870 | 0.318 | 0.848 | 0.000 | 9 | 9 |
| db6dfba | absence proof, channel diagnostics | 0.955 | 0.870 | 0.318 | 0.848 | 0.000 | 9 | 9 |
| ea71021 | linking diagnostics | 0.955 | 0.870 | 0.318 | 0.848 | 0.000 | 9 | 9 |
| 84c14b9 | reference following, image evidence | 0.955 | 0.875 | 0.364 | 0.848 | 0.000 | 2 | 0 |
| ce57f8e | images, reference following | 0.955 | 0.875 | 0.364 | 0.848 | 0.000 | 2 | 0 |
| 84fe0de | replica drift, activity category, zero-link rule | **1.000** | **0.920** | **0.409** | 0.848 | 0.000 | 2 | 0 |
| session 3 | validator warning, PDF fallback, own cases, docs | 1.000 | 0.920 | 0.409 | 0.848 | 0.000 | 2 (warnings) | 0 |
| session 4 | account finder + inventory-table coverage | **1.000** | **0.944** | **0.636** | **0.857** | 0.000 | 2 (warnings) | 36 |
| session 5 | account propagation + intent negation table | 1.000 | 0.944 | 0.636 | 0.857 | 0.000 | 2 (warnings) | 45 (9 more than session 4) |

**Per option** (`compare.py`, final code with options toggled):

| config | dev status | dev P | dev R | dev F1 | dev exact | dev linkR | dev linkP | recovered / extra vs base |
|---|---|---|---|---|---|---|---|---|
| base | 0.955 | 0.951 | 0.802 | 0.870 | 0.318 | 0.723 | 0.979 | — |
| + follow_refs | 0.955 | 0.951 | 0.810 | 0.875 | 0.364 | 0.738 | 0.980 | 1 / 0 |
| + images only | 0.955 | 0.951 | 0.802 | 0.870 | 0.318 | 0.723 | 0.979 | 0 / 0 |
| follow + images | 0.955 | 0.951 | 0.810 | 0.875 | 0.364 | 0.738 | 0.980 | 1 / 0 |
| + replica_any | 1.000 | 0.962 | 0.835 | 0.894 | 0.409 | 0.738 | 0.980 | 1 / 0 |
| + replica_drift | 1.000 | 0.962 | 0.835 | 0.894 | 0.409 | 0.738 | 0.980 | 1 / 0 |
| + activity category | 1.000 | 0.990 | 0.860 | 0.920 | 0.409 | 0.738 | 0.980 | 1 / 0 |
| + account finder | 1.000 | 0.973 | 0.884 | 0.926 | 0.545 | 0.815 | 0.981 | 5 / 0 † |
| + table coverage only | 1.000 | 0.990 | 0.860 | 0.920 | 0.409 | 0.738 | 0.980 | 0 / 0 † |
| **+ account finder + table coverage (final)** | **1.000** | **0.991** | **0.901** | **0.944** | **0.636** | **0.815** | **0.981** | 5 / 0 † |

† recovered / extra relative to "+ activity category" (`compare.py drift+actcat account table_cover account+cover`).

Held-out is identical in every config up to "+ activity category": status 1.000, P 1.000, R 0.736,
F1 0.848, exact 0.000, linkR 0.630, linkP 1.000. With the account finder: R 0.750, F1 0.857, linkR 0.652,
linkP 1.000 (1 recovered, 0 extra). The planner oracle is 4/4 in every config.
Images change no sample score. In the 518-case run, the final config with `images=False` has 9
empty-COMPLETE rows and with `images=True` it has 2. At commit level, 9 rows changed (commit table).

**Session 6 (review fixes, no output change):**
- Without pdftotext, the test suite had 1 error: a test helper called the PDF reader without a file id, so
  the committed-text fallback could not be found. Fixed, with a regression test. 113 tests now pass with and
  without pdftotext (3 skipped without it). 0 of 518 rows changed, and every metric is unchanged.
- The split description now states that held-out aggregates were a no-regression gate and that the
  one-account premise counts all 32 samples.

**Session 5 (propagation, forced pick, negation):**
- Constraint propagation (`account_finder.propagate`, default on). An account belongs to one user. The pool is every
  deletion request in `dataset/` (518 + 32 samples, no shared case_ids). Accounts that evidence links to a request's
  user start as taken. Each round decides every unresolved request on its remaining candidates, with the same
  single-survivor / user-number rule. If two users pick the same account in one round, neither gets it. Picks are
  final.
  Rounds resolve 48, 2 and 1 requests; requests still needing an account go 362 → 314 → 312 → 311.
  Dev picks: 5 correct, 0 wrong, precision 1.000 in every round (same as the kept finder). Held-out: 1 / 0.
  518 picks 36 → 42 → 44 → 45. No sample metric changes, so the 9 extra 518 picks are untested on labels.
  Kept under the rule (dev precision ≥ 0.95, no regression).
- After propagation, 311 requests remain without an account: 300 with ≥ 2 candidates and 11 with none
  (287 and 10 of them in the 518).
- 518-case run: 9 rows change, each only by adding one account (6 INCOMPLETE and 3 COMPLETE; no status flip,
  nothing lost). VALID, 0 invalid, 2 warnings, deterministic. 112 tests pass.

**Session 4 (account finder):**
- Rule (`code/ghost/account_finder.py`, tests `code/tests/test_account_finder.py`): every case has exactly one
  account record. If linking found one, nothing changes. Otherwise the candidates are account DELETE_RECORD rows
  from 75 min before to 10 min after reported_at (≤ audit_at). Accounts that evidence ≤ audit_at ties to any
  identifier other than the subject's are removed. The user-number pattern only breaks a tie among survivors, and
  if the choice is still ambiguous nothing is chosen.
- Account picks: dev 11 cases needed one, **5 recovered, 0 wrong, 6 abstained, precision 1.000** (≥ 0.95, kept).
  Held-out aggregate: 9 needed one, 1 recovered, 0 wrong, 8 abstained.
- Found accounts proved absent were first cited to an older inventory file. Gold cites the latest SQL dump
  holding the `customer_profiles` tables, so `parse_sql(table_coverage=True)` makes such a dump coverage for its
  system. Dev P 0.973 → 0.991, exact 0.545 → 0.636.
- 518-case run: 36 rows change, each only by adding one account record (25 INCOMPLETE and 11 COMPLETE, with no
  status flip and no resource lost). Rows with an account: 166 → 202 of 508. Still VALID, 0 invalid, 2 warnings.
  Deterministic.

**Session 3:**
- `validate.py`: COMPLETE with `[]` is now a warning. On the final `output.csv`: **VALID, 0 invalid rows, 2 warnings**.
- PDF fallback: with `pdftotext` removed from PATH, `output.csv` is byte-identical (`cmp`), and 4 warnings are logged.
- Own cases: 3/4 pass. The failure is reported in section 5 and not fixed.
- Test suite: 92 tests, all pass (`python3 -m unittest discover -s code/tests`); 102 after session 4.
- `code.zip` check: unpacked into an empty directory with `dataset/` linked in, `main.py` reproduces the root
  `output.csv` byte for byte. The suite passes there too (92 tests, 1 skipped). The planner-oracle table test now skips
  when `problem_statement.md` is absent, because the documented zip command does not include that file.

## 10. Final 518-case output checks

`python3 code/main.py`: INCOMPLETE 356, COMPLETE 152, NOT_APPLICABLE 10. Steps per case: min 0,
median 6, max 14, total 2736. Accounts found by the finder (with propagation) 45, category fallbacks 0, state coercions 0. `validate.py`: VALID, 0 invalid
rows, 2 warnings (zero-link COMPLETE `[]`). Two runs are byte-identical, and so are runs with and without pdftotext.
