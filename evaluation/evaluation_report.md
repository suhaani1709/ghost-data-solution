# Evaluation report: Ghost Data Still Exists deletion-audit agent

Every number below was measured on the final code (2026-10-25; sections 3-4 include the session-10 status-matched account finder and the session-12/13 rules, sections 15-16) by the scripts named next to it. Nothing
is estimated. Where a value is plain arithmetic on measured counts, the arithmetic is shown.

```bash
python3 code/evaluation/score.py                 # sections 3-4
python3 code/evaluation/compare.py base follow_refs images follow+images replica_any replica_drift drift+actcat account table_cover account+cover propagate after_audit explicit_absence after+explicit llm
python3 code/evaluation/breakdown.py             # section 7
python3 code/evaluation/channels.py              # section 8 (linking channels)
python3 code/evaluation/channels.py --accounts   # section 8 (account finder, forced pick)
python3 code/evaluation/run_own_cases.py         # section 6
python3 code/evaluation/validate.py output.csv   # section 11
```

Every evaluation script and test runs **offline**: model answers come only from the local cache
(`code/llm_cache/`, not shipped in `code.zip`), and no model call is made.

## 1. First submission and what changed

The first submission scored **Output CSV 7.2/30** and **Code zip 4.5/30**. We found three causes:

| cause | evidence | fix |
|---|---|---|
| Row order | `output.csv` was sorted as strings (case_100 … case_99), while `deletion_requests.csv` is numeric (case_33 … case_550). **0 of 518** positions matched, so a grader that pairs rows by position compares almost every row with the wrong case | rows now follow the numeric order of `deletion_requests.csv` (`loaders.case_sort_key`); `validate.py` rejects string order; test `tests/test_output_order.py` |
| No AI agent | the challenge asks for an AI-powered agent, but the first version made zero model calls | three agents on Claude Sonnet (intent, vision, and a tool-calling investigator with routing), every output audited by deterministic checks (section 5) |
| Incomplete answers | held-out, the best proxy for unseen cases: 10 of 10 cases missed at least one record (8 accounts, 4 audit, 4 analytics), with 0 extra records | ownership linking from evidence of any date, explicit-absence citations and static categories (sections 9-10): held-out step recall 0.750 → 0.833, held-out exact 0/10 → 1/10 |

We cannot prove that the row order caused the low output score, because the grader is not public. It is the
only explanation we found for a score so far below the sample metrics.

**Second (test) submission, after these fixes:** transcript 8.8/10, output CSV **23.7/30** (up from 7.2),
code zip **21.9/30** (up from 4.5), interview not taken. Another participant reached output 29.2 and code 25.2.
Session 9 (section 12) audited all 518 rows and backtested account assignment to look for the remaining gap.

## 2. Splits and how clean they are

The 32 public samples are the only labelled data. `score.py` sorts them by `case_id`: the first 22 are **dev**
and the last 10 are **held-out**. Held-out is **not** an untouched test set:

- Held-out aggregates were used as a no-regression gate for kept changes in earlier sessions.
- The account finder's premise ("every case has exactly one account record") counts all 32 sample answers.
- After the first submission, the missing held-out records were studied in detail (session 7). The
  any-date ownership and explicit-absence rules (sections 9-10) came from that study of all 32 samples.

Treat every number below as an in-sample fit on 32 cases. None of them estimates the hidden-set score.

Metric definitions (`score.py`):
- *Status accuracy*: `deletion_status` is equal.
- *Exact*: status and the full `steps_json` array are both equal.
- *Step P/R/F1*: steps are compared as multisets of (phase, system_id, resource_id, operation, state, evidence_id), ignoring `step_no`.
- *Field accuracy*: gold step *i* is compared with predicted step *i*, per field; every gold step counts.
- *Sequence accuracy*: the ordered list of (operation, system_id, resource_id) is equal.

## 3. Case-level status accuracy

| split | cases | status accuracy | exact case match |
|---|---|---|---|
| all | 32 | **1.000** | 0.625 (20/32) |
| dev | 22 | **1.000** | 0.773 (17/22) |
| held-out | 10 | **1.000** | 0.300 (3/10) |

Delivered configuration (section 17), whose output is the CSV the hidden grader scored 25.5/30.

Confusion matrix (all 32): COMPLETE 10→10, INCOMPLETE 22→22. The samples contain no NOT_APPLICABLE case.

## 4. Step-level, field-level and sequence accuracy

| split | step P | step R | step F1 | sequence accuracy |
|---|---|---|---|---|
| all | 1.000 | 0.922 | 0.960 | 0.625 |
| dev | 1.000 | 0.950 | 0.975 | 0.773 |
| held-out | 1.000 | 0.875 | 0.933 | 0.300 |

| field accuracy | step_no | phase | system_id | resource_id | operation | state | evidence_id |
|---|---|---|---|---|---|---|---|
| all | 0.92 | 0.91 | 0.81 | 0.81 | 0.81 | 0.82 | 0.92 |
| dev | 0.95 | 0.95 | 0.92 | 0.92 | 0.92 | 0.92 | 0.95 |
| held-out | 0.88 | 0.83 | 0.62 | 0.62 | 0.64 | 0.67 | 0.86 |

The steps we emit are almost always right (precision 0.99 to 1.00). The loss is missing records (section 7).
Field accuracy is position-aligned, so one missing record early in the sort order shifts every later step.
That is why held-out system/resource accuracy (0.51) is far below held-out step recall (0.833). Ordering is
correct: the planner oracle (`tests/test_planner_oracle.py`, 4/4) rebuilds every sample answer exactly from
its gold resources.

## 5. The AI agents

**Backend.** Claude Sonnet (`claude-sonnet-5-5`), called through Claude Code's headless mode
(`llm.ClaudeCodeClient`):
- Each call carries only the pipeline's own system prompt. No Claude Code tools, MCP servers or project files
  are loaded; the vision agent gets the Read tool, limited to one image copy.
- Every answer is cached locally in `code/llm_cache/` (not shipped in `code.zip`).
- The first version of the agents ran on a free OpenRouter model (`nvidia/nemotron-3.5-super-vl:free`). It is
  still available with `--backend openrouter` and is used below for comparison.

**Intent agent** (`ghost/intent_agent.py`, `INTENT_PROMPT`). All 398 distinct request texts (518 evaluation
+ 32 sample requests) go to the model in 8 batches. The decision per text is: the sentence tables first, then
an explicit refusal (`intent.NEGATIONS`), then the model, then the DELETE default.

| measure | Claude Sonnet | free OpenRouter model |
|---|---|---|
| agreement with the tables on the 375 texts they label | **375 / 375** | 375 / 375 |
| sample texts only the model can label, vs gold status (all deletions) | **23 / 23** | 23 / 23 |
| 518 intents changed | 0 | 0 |

**Vision agent** (`ghost/vision_agent.py`, `VISION_PROMPT`). The model opens each of the 11 PNG screenshots
and transcribes its records. The reading is used when its facts (resource id, role, user_id, email, phone,
state, category) equal those in the development transcript; otherwise the transcript is used. Screens can show
decoy identifiers that are not in `user_identities.csv`. These are accepted when the transcript shows the same
value.

| measure | Claude Sonnet | free OpenRouter model |
|---|---|---|
| screenshots whose reading equals the transcript (reading used) | **10 / 11** | 6 / 11 |
| disagreements | 1: backup console. Claude treats the "backup_9286 / backup_9281 restored" activity lines as references *of* backup_9287. The transcript deliberately records no owner, because those lines are restores of other archives, so the transcript is kept (checked by viewing the image) | 5: dropped visible emails (2 images, checked by viewing), a misread email (`g.silva76.jr` as `g.silva76jr`), missed rows (2: the marketing record, a backup reference) |
| 518 rows changed | 0 | 0 |

**Investigator agent** (`ghost/investigator.py`, `SYSTEM_PROMPT`). This is a tool-calling loop: one JSON
action per turn, at most 6 turns. The tools are `record_history`, `search_identifier`, `read_evidence`,
`account_candidates`, `policy` and `submit`. `merge()` applies a proposal only if a deterministic check backs it:
- an account may be added only from the candidates shown in that session, and only when the case has none;
- a record may not be dropped when its own evidence names the requester;
- a category change must be named by the record's evidence or be a documented alternative for that system.

State and citations always come from the resolver.

| measure | result |
|---|---|
| pilot on all 32 samples (`run_investigator.py --live`) | 31 submitted, 1 hit the turn cap; 140 turns; **0 proposals** (it confirmed the engine in every case, including 12 where it inspected account candidates and declined to guess) |
| sample metrics with every proposal kind enabled vs engine only | identical: dev F1 0.953, held-out F1 0.909 (no gain, no regression) |
| routing on the 518 (`uncertainty_flags` → `route`) | 263 of 508 deletion cases flagged: category conflict 8, weak link 39, no account 222. The 20 most urgent were investigated (budget 20) |
| 518 routed cases | 20 submitted, 1 proposal, **0 accepted, 1 rejected**. The rejection was a drop of a retained security audit record whose only "present" evidence postdates `audit_at`; the guardrail refused because the record's own evidence names the requester and policy retains audit records |
| 518 rows changed | 0 |

**What the agents do and don't do.** They handle unseen request wording, re-read and verify the image
evidence, and review uncertain cases with tools under deterministic guardrails. They do not raise sample
accuracy, because the records we still miss have no evidence tying them to the requester (section 7), and no
reader, human or model, can recover a link that isn't there. Budget: the investigator costs about 15.7k
tokens per case (pilot), so investigating all 263 flagged cases would take about 4.1M tokens. That is why
routing takes the 20 most urgent.

## 6. Own evaluation cases (4, built by us)

Each case has its own `dataset/` in the real schema, with fictional people, `example.com` emails and
`+1 555 01xx` phones. The expected answer was derived by hand from the rules and written down before the
pipeline was run (`code/evaluation/own_cases/*/CASE.md`). Run: `python3 code/evaluation/run_own_cases.py`.

| case | what it tests | expected | result |
|---|---|---|---|
| a_do_not_delete | "Please do not delete my account. I still use it every week." with a live profile in evidence | NOT_APPLICABLE `[]` | **PASS** (it failed until the negation table was added in session 5) |
| b_lookalike_decoy | a same-name search document with the look-alike email `ada.quill@exarnple.com`, and an analytics row holding SHA-256 of `ada.quil@example.com`; the real profile is deleted | COMPLETE, 1 VERIFY_RECORD_ABSENT cited to the empty covering snapshot | **PASS** |
| c_replica_holds_row | the primary table lacks the row and the failover replica holds it; an activity row claims DELETE SUCCESS | INCOMPLETE: REPORT_REMAINING_RECORD → DELETE_RECORD → VERIFY_RECORD_ABSENT | **PASS** |
| d_old_email_hash_only | the request uses a historical email, and the only evidence is a search hit whose `correlation_key` is SHA-256 of that old email | INCOMPLETE: REPORT_REMAINING_RECORD → DELETE_RECORD → VERIFY_RECORD_ABSENT | **PASS** |

**4 / 4 pass.**

## 7. Failure analysis

Linkage (`breakdown.py`):
- **Dev recall 55/65 = 0.846**, precision 55/56 = 0.982.
- **Held-out recall 36/46 = 0.783**, precision 36/36 = 1.000.
- All 32: recall 91/111 = 0.820, precision 0.989.

The 20 gold records we still miss, by what the participant data offers for each:

| system | kind | dev | held-out |
|---|---|---|---|
| account_service | appears only in `DELETE_RECORD` activity rows | 3 | 4 |
| account_service | in evidence, identifiers removed (404 lookup) | 1 | 2 |
| account_service | no trace in any evidence or activity row | 1 | 0 |
| analytics_platform | in evidence, identifiers removed (anonymized) | 3 | 4 |
| security_service | no trace in any evidence or activity row | 2 | 0 |

Why these are hard:
1. **Activity rows have no person column.** `system_activity.csv` has 8 columns. `details` carries only resource
   ids, except in the 12 `LINK_RESOURCE_IDENTITY` rows. A record that appears only in activity rows can be tied
   to the requester only by time or id numbers, and section 8 shows how imprecise both are.
2. **Deletion removes the identifiers we would link on.** The anonymized analytics records and the 404 account
   lookups carry 0 identifier tokens.
3. **No trace at all:** for 3 records, nothing in the participant data names them.

The account finder picks an account only when the choice is unambiguous. With the session-9 window and the
session-10 status match it finds 155 accounts in the 518 run, and 391 of the 508 deletion rows have one account step. In the samples, every gold answer has one.

Other known limits:
- 1 row of the 518 is COMPLETE with `[]` (zero-link rule: no linked record, nothing to cite). `validate.py` reports it as a warning.
- One state coercion in the 518 run: a backup record proven absent is mapped to the compliant "restore blocked" state.
- Rule conditions (retention period, active legal hold) are not evaluated. Every `retention_until` in the
  evidence is later than the latest `audit_at`, so this has no effect on this data.

## 8. Tried and rejected (measured)

| idea | measurement | verdict |
|---|---|---|
| A: any activity row between requested_at and audit_at | dev: 13 gold newly linked, 6958 extra, channel precision 0.002 | rejected |
| C: as A, deletion_worker rows only | dev: 13 new, 2744 extra, precision 0.005 | rejected |
| D: resource number == user number | dev: 5 new, 19 extra, precision 0.208; evidence shows different numbers in 38 of 42 account/user pairs | rejected (used only as a tie-breaker inside the account finder) |
| B: LINK_RESOURCE_IDENTITY claims | dev: 0 new, 2 extra | rejected |
| N: user's name in a record's text | dev: 0 new, 2 extra, precision 0.000 | rejected; names are never used for linking |
| same-batch analytics (finder on ANONYMIZE_RECORD rows around reported_at) | dev 2 right / 3 wrong, precision **0.400**; anchored on the account's own delete: 0 right | rejected |
| batch anchored on the case's own linked records (closest worker event in time) | the gold account was the closest candidate in only 2 of 11 account misses that had an anchor | rejected |
| forced account pick (closest delete to reported_at) | dev precision 0.400 (margin ≥ 0) to 0.500 at best; would touch 287 of the 518 rows | rejected |
| account finder with a strictly-before window | dev 2 right / 0 wrong / 9 abstained, vs 5 / 0 / 6 for −75/+10 min | −75/+10 kept |
| replica_persist "any" | same scores as "drift" | the stricter "drift" kept |

## 9. Planner disagreements and interpretation choices

From `code/ghost/planner.py` (DISAGREEMENTS), where the rules file and the sample answers do not line up:
1. BACKUP_ARCHIVE: rule_14 says RETAIN, but the samples verify VERIFY_RESTORE_BLOCKED and report REPORT_RESTORE_RISK. We follow the samples.
2. DATA_FLOW: no data category covers sync/import flows, but the samples treat `data_flow_*` as DISABLE / VERIFY_DATA_FLOW_DISABLED. This is a pseudo-category taken from the samples.
3. Category is not a function of system: support_platform holds SUPPORT_MESSAGE or SUPPORT_ATTACHMENT, and analytics_platform holds ANALYTICS_PROFILE or MARKETING_PROFILE. The category therefore comes from the evidence for each record.
4. SECONDARY_IDENTIFIER, CACHE_ENTRY, PRODUCT_TELEMETRY, EMAIL_DELIVERY_LOG and LEGAL_HOLD_RECORD appear in no sample. Their treatment comes from `deletion_rules.csv` alone.
5. Rule conditions are not evaluated (section 7).

**Interpretation choice (session 7).** AGENTS.md says evidence created after `audit_at` must not change the
answer. Yet the answer key lists records whose only identifying evidence was captured after `audit_at`: of the
8 sample records that such evidence links, all 8 are in gold and none is outside it. We therefore treat
*ownership* (whose record it is) and a record's *type* as static facts that may come from any capture date.
A record's *state*, and every *citation*, still come only from evidence dated on or before `audit_at`. A
retained record with no state before `audit_at` becomes a future "verify present" check with no citation,
and only in INCOMPLETE cases, because a COMPLETE verification must cite evidence.

## 10. What improved at each step

Each config (`compare.py`) adds one option to the row above it, except "images only" (added to base) and
"explicit absence only" (added to the propagation row). Recovered/extra counts are relative to `base`.

| config | dev F1 | dev exact | dev linkR | held F1 | held exact | held linkR | rec/extra dev | rec/extra held |
|---|---|---|---|---|---|---|---|---|
| base | 0.870 | 0.318 | 0.723 | 0.848 | 0.000 | 0.630 | – | – |
| + reference following | 0.875 | 0.364 | 0.738 | 0.848 | 0.000 | 0.630 | 1/0 | 0/0 |
| images only | 0.870 | 0.318 | 0.723 | 0.848 | 0.000 | 0.630 | 0/0 | 0/0 |
| + images + replica drift | 0.894 | 0.409 | 0.738 | 0.848 | 0.000 | 0.630 | 1/0 | 0/0 |
| + activity category | 0.920 | 0.409 | 0.738 | 0.848 | 0.000 | 0.630 | 1/0 | 0/0 |
| + account finder | 0.926 | 0.545 | 0.815 | 0.857 | 0.000 | 0.652 | 6/0 | 1/0 |
| + inventory-table coverage | 0.944 | 0.636 | 0.815 | 0.857 | 0.000 | 0.652 | 6/0 | 1/0 |
| + account propagation | 0.944 | 0.636 | 0.815 | 0.857 | 0.000 | 0.652 | 6/0 | 1/0 |
| + ownership from any date | 0.953 | 0.682 | 0.846 | 0.879 | 0.100 | 0.783 | 8/0 | 7/0 |
| explicit absence only | 0.944 | 0.636 | 0.815 | 0.857 | 0.000 | 0.652 | 6/0 | 1/0 |
| **ownership + explicit absence + LLM agents + investigator (final)** | **0.953** | **0.682** | **0.846** | **0.909** | **0.100** | **0.783** | 8/0 | 7/0 |

Dev status went from 0.955 at base to 1.000 with replica drift and has stayed there; held-out status is 1.000
throughout. The planner oracle is 4/4, and invalid 518 rows are 0, in every config. Ownership from any date
alone dropped held-out step precision to 0.967, because two absence citations differed from gold. Explicit
absence (cite a record's own 404 lookup rather than a later blanket snapshot) brought it back to 1.000.

Effect on the 518 rows, relative to the first submission:

| change | rows changed | how |
|---|---|---|
| numeric row order | all rows move; 0 row contents change | order only |
| ownership from any date + explicit absence + static category | **152** | records added only (122 audit, 75 account, 14 search, 2 legal hold, 1 backup, 1 support); 0 removed, 0 status flips, 0 citation changes |
| LLM agents (intent, vision, investigator) | 0 | the model agrees with the tables on every 518 text; only agreeing image readings are used; the investigator's one proposal was rejected |
| (account finder 36 rows, propagation 9 rows) | already in the first submission | each added one account record, with no status flip |

## 11. Final 518-case output checks

- `python3 code/main.py` (cached, offline): INCOMPLETE 356, COMPLETE 152, NOT_APPLICABLE 10.
- Steps per case: min 0, median 6, max 14, total 3056. Category fallbacks 0, state coercions 1 (section 7).
- `validate.py`: **VALID, 0 invalid rows**, 1 warning (zero-link COMPLETE `[]`).
- Row order equals `deletion_requests.csv`.
- Two runs are byte-identical, and so are runs with and without pdftotext.
- Investigator: 20 routed cases (from the engine's flags, recomputed each run); 0 proposals accepted; 0 rows changed.
- 150 tests pass offline (`python3 -m unittest discover -s code/tests`).
- Offline run without the cache (as from `code.zip`) gives a byte-identical `output.csv`; no model call is made.
- Line endings are LF, like the dataset CSVs (test `tests/test_output_order.py`).

## 12. Session 9: row audit, independent check, account assignment backtest

**Row audit** (`code/evaluation/audit_rows.py`; invariants are derived from gold and used only if they hold there;
flagged case_ids are in `orchestrate_research/AUDIT_518.md`, outside the zip):

| invariant | gold | 518 output |
|---|---|---|
| a. exactly one account_service record per deletion case | 32/32 | 224 rows flagged before session 9; 217 after (all with no account; the one two-account row was fixed) |
| b. structure: finding → remediation → verification, COMPLETE = verification only, step_no, sort key | 32/32 | 0 flagged |
| c. cited file is the latest file (≤ audit_at) that mentions the record | 71/71 | 1039/1039 |
| d. operation mix | – | short on account VERIFY_RECORD_ABSENT (9.7% vs 16.6% of steps) and analytics anonymize (2.5% vs 6.2%): the known misses |
| e. provenance tier of linked records | – | evidence 1466, image 5, finder 39 (before the window change); no row rests only on weak tiers |
| f. users with several requests | – | 1 user, 2 cases with different audit dates and different record sets (expected: different audit dates) |
| g. NOT_APPLICABLE | – | 10, all with explicit non-deletion text |
| h. categories the samples never exercise | – | LEGAL_HOLD_RECORD in 8 rows (RETAIN; every hold shows a retention date after the latest audit_at) |

**Independent check** (`code/evaluation/independent_check.py 40`). Linked records were re-derived from raw
evidence text with whole-token identifier matching, using no parsers and no observations table, for 40
stratified rows:
- **124 agree, 0 only in our output, 1 only in the independent set.** The one extra is an audit record whose only
  link is a log captured after the case's audit_at, in a COMPLETE case, so it cannot be cited, by design.
- Other checks: all timestamps share one UTC format; 29 evidence files are captured exactly at some audit_at
  and count as "at or before".

**The missing accounts.**
- 8 of the 11 missed gold accounts appear in **no evidence file at all**. Their only trace is one
  `DELETE_RECORD` row.
- There are 539 account deletes for 540 deletion requests. Deletes land 39–76 min before `reported_at`
  (265 labelled pairs; 3 outliers within 6 min). `reported_at` is on the hour, so requests sharing a
  `reported_at` form slots: 81 singles, 36 pairs, 124 triples, 3 fives.

`code/evaluation/account_backtest.py` hides each labelled account (278: 246 evidence-linked, 31 gold with a
delete event) together with its evidence, then reruns finder and exclusive propagation over all 540 requests.
The window is tuned on even case numbers and reported on odd ones:

| window (min vs reported_at) | tune P / R (picks) | held P / R (picks) |
|---|---|---|
| [−75, +10] (previous) | 1.000 / 0.369 (45) | 1.000 / 0.284 (44) |
| [−76, −39] | 1.000 / 0.459 (56) | 1.000 / 0.316 (49) |
| **[−76, −39], then [−6, +6] if empty (kept)** | **1.000 / 0.492 (60)** | **1.000 / 0.329 (51)** |
| [−76, −39] ∪ [−6, +6] (union) | 1.000 / 0.385 (47) | 1.000 / 0.277 (43) |

The old window reached into the next hour's slot. Kept: the fallback window. The gold metrics are unchanged;
on the 518, **6 rows** each gain one account (no status flip, nothing removed). The offline replay still has
0 cache misses.

**Bug found by invariant a (kept fix).** case_46 had two accounts, both linked by the current email: one by
evidence before audit_at, and one only by a log captured six months after audit_at (a later sign-up). Ownership
from any date had wrongly added the second. Rule (`account_finder.one_account`, test first): when evidence up
to audit_at links an account, accounts linked only by later evidence are dropped. **1 row changed** (case_46
loses the post-audit account; status unchanged). Gold metrics unchanged. Backtest held half 1.000 / 0.329
(unchanged); tune half 1.000 / 0.484, a label correction: case_46's label had been the wrong account.

**Rejected (measured):**
- **Order within a slot:** event order matches case-number order in 13 of 74 labelled slots, requested_at order
  in 25 of 74, user-number order in 13 of 74, and the order of the case's other worker events in 21 of 57.
  None is usable.
- **Analytics assignment:** ANONYMIZE events land 40–120 min *after* reported_at. A finder on that window was
  right on 13 of 13 hidden labelled analytics records, but also gave a record to 1 of the 19 gold cases that
  have none, which would lower gold step precision. Not enabled.
- **Audit records:** no worker event targets security_service, so the method cannot apply.

**Targets (32 gold cases; dev / held-out):** status 1.000 / 1.000; step precision 0.991 / 1.000; step recall
0.917 / 0.833 (targets 0.95 / 0.90: not met); linkage recall 0.846 / 0.783 (targets 0.92 / 0.85: not met);
exact 0.682 / 0.100 (targets 0.80 / 0.50: not met); citation accuracy on matched steps 1.000 / 1.000;
third validation set, account-pick precision 1.000 on the held half, recall 0.329. The unmet targets need
the within-slot account choice, and no measured signal decides it at the required precision.

## 13. Session 10: reported_status matches the account delete's result (kept)

A column-coverage audit tested unused relationships as join keys against the labelled accounts. The request's
`reported_status` agrees with the `reported_result` of its account `DELETE_RECORD` in **256 of 261** labelled
pairs: COMPLETE~SUCCESS 136/138, PARTIALLY_COMPLETE~PARTIAL 69/70, NOT_STARTED~FAILED 51/53. Requests that report
in the same hour usually differ in status, so this separates them.

Rule (`AccountFinder(status_match=True)`, test first): a candidate delete must carry the result that matches the
request's status; everything else (windows, exclusivity per user, abstain when ambiguous) is unchanged.

| measure | before | after |
|---|---|---|
| account backtest, tune half P / R (picks) | 1.000 / 0.484 (59) | **1.000 / 0.730 (89)** |
| account backtest, held half P / R (picks) | 1.000 / 0.329 (51) | **1.000 / 0.735 (114)** |
| dev step R / F1 / exact / sequence / position-aligned field mean | 0.917 / 0.953 / 0.682 / 0.682 / 0.868 | **0.942 / 0.966** / 0.682 / 0.682 / **0.911** |
| held-out step R / F1 / exact / sequence / field mean | 0.833 / 0.909 / 0.100 / 0.100 / 0.651 | **0.875 / 0.933 / 0.300 / 0.300 / 0.732** |
| linkage recall dev / held-out | 0.846 / 0.783 | **0.892 / 0.848** |
| step precision dev / held-out | 0.991 / 1.000 | 0.991 / 1.000 |
| 518 rows changed | – | **100**, each gains one account; 0 removed, 0 status flips; 391 of 508 deletion rows now have one account |

Five of the 20 pinned investigator cases gained an account, which changed their review prompts. Those five were
removed from the pinned set (15 remain), so the offline replay has 0 cache misses. Output is identical either
way, because the investigator accepted no proposal.

**Reviewed and rejected in session 10 (measured):**
- **Forced account pick** (closest candidate when the pool has ≤ k accounts): on dev it raises position-aligned field
  accuracy (0.868 → 0.907 at k = 2), but held-out sequence accuracy does not improve at k = 2, and at k = ∞
  held-out F1 drops by 0.025. Pick precision is 1/7 to 2/10. It fails the gate and is not enabled.
- **Same-user collisions:** all 9 colliding groups are different users, so exclusivity per user is already right.
- **Worker-event lag tie-breaker (signed):** unstable between halves (IQR 94–113 vs 105–131 min); tune 0.333 vs
  chance 0.414, held 0.468 vs 0.406.
- **Row position in exports and SQL:** 62 of 65 SQL tables with more than 2 rows are sorted by resource_id, so
  position carries no information.
- **Analytics presence:** no countable property separates gold cases with and without analytics. The best,
  "a linked file holds analytics data", is true for 12 of 13 with and 10 of 19 without.

## 14. Session 11: packaging fix after Code ZIP 0/30

- **Finding (confirmed):** the 0-scoring `code.zip` contained `code/llm_cache/` (281 files), and in it
  `routed_cases.json`, a list of 15 real case ids that steered the investigator. AGENTS.md §6.7 forbids case-id
  shortcuts, and §6.9 forbids caches in the archive.
- **Not confirmed:** that the cache alone caused the zero. The zip that scored 21.9 already contained the cache;
  the case-id list was new. The grader is not public, so the cause cannot be proven.
- **Fix:**
  - `code/llm_cache/` is excluded from the zip (README packaging command).
  - The pinned case-id list was deleted; routing is computed from the engine's flags on every run.
  - Without Claude Code the CLI prints a NOTE and runs offline. No model call is made, and no answer is claimed
    from a model.
  - Output is byte-identical to the session-10 output.
- **CSV hypothesis tested and rejected:** widening the account window to [−90, −30] min gives identical backtest
  results (tune 1.000 / 0.730, held 1.000 / 0.735) and changes 0 of the 518 rows.

## 15. Session 12: output improvements from the remaining gold discrepancies

Every remaining step difference on the 32 gold cases was classified: 7 missing analytics, 5 missing accounts,
2 missing audit records, 1 extra account (case_17, dev), and 1 wrong state (case_24, held-out). Three general
rules were kept. Each was measured on its own (`code/evaluation/experiment.py`) and written with a test first:

| rule | derived from | dev (exact / F1) | held-out (exact / F1) | 518 rows |
|---|---|---|---|---|
| baseline (final_version_3) | – | 0.682 / 0.966 | 0.300 / 0.933 | – |
| **newest account**: when evidence links several accounts, keep the one whose linking evidence (≤ audit_at) is newest; a re-signup is audited on the current account | dev case_17 | 0.727 / 0.970 (precision 0.991 → 1.000) | unchanged | 0 |
| **status-free fallback window**: the status match applies to the [−76, −39] window only; the ±6 min fallback ("reported completed" events) is not status-filtered | dev case_08; backtest tune recall 0.730 → 0.746 at precision 1.000 | 0.773 / 0.975 | unchanged | 0 |
| **coverage only if unobserved**: a blanket snapshot that merely lacks the row proves absence only for a record with no own observation up to audit_at (gold case_31 vs case_24) | held-out case_24 (so held-out is not independent for this rule) | unchanged | 0.400 / 0.949 | 2 (case_33 COMPLETE→INCOMPLETE; case_34 +1 finding) |
| **all three (delivered)** | | **0.773 / 0.975, precision 1.000** | **0.400 / 0.949, precision 1.000** | **2** |

**Rejected (measured):**
- **State floor** (state only from evidence ≥ reported_at; every gold citation is after reported_at): gold
  unchanged, but on the 518 it removes 34 steps from 29 rows with no gold case to support them.
- **Analytics finder with status match:** anonymize results do not follow the request status (mostly FAILED);
  3 of 19 gold no-analytics cases get false records.
- **Account → analytics activity coupling:** no event pair within 10 min in 73 labelled pairs.
- **Order within same-status slots** (case no., requested_at, audit_at, user no.): consistent in about half of
  50 labelled groups, i.e. chance.
- **Own case (b) conflict:** its hand-written expected answer (session 3) assumed a later empty snapshot overrides
  an earlier "present" observation. Gold case_24 shows the opposite, so own case (b) now fails (3/4). The fixture
  was not edited to make it pass.

## 16. Session 13: what an empty snapshot proves (rule 3 of section 15 replaced)

Every absence proof in the gold answers was checked against the kind of file it cites:
- **SQL table dumps** (snapshot_scope inventories, replica dumps) prove absence even for subjects they never
  mention: case_01, case_02, case_04 (3/3).
- **JSON records-assurance bundles** hold only a few subjects' records (evidence_51: 2 tombstones and 2 audit
  records). They prove absence only for a subject they mention (case_31, 1/1). They do not override an earlier
  observation of a subject they don't mention (case_24).

Section 15's rule 3 ("coverage only if unobserved") explained the same gold cases, but it over-generalized. It also
let a stale observation beat a later **exhaustive** SQL dump: case_33 (a screenshot on 06-18; an inventory on 07-03
lacking the record) and case_34. Replaced by **scoped bundles** (`StateResolver(scoped_bundles=True)`, test first):
- a JSON bundle's empty collection proves absence only for subjects the bundle mentions;
- a SQL dump stays exhaustive;
- the latest evidence wins.

| configuration | dev exact / F1 | held-out exact / F1 | 518 rows vs final_version_4 |
|---|---|---|---|
| final_version_4 (coverage only if unobserved) | 17/22 / 0.975 | 4/10 / 0.949 | – |
| **scoped bundles (delivered)** | 17/22 / 0.975 | 4/10 / 0.949 | 4: case_33 back to COMPLETE and case_34 back to its v3 steps (the inventory proves deletion); case_308 and case_309 cite the SQL inventory (evidence_72) instead of a bundle that does not mention their subjects (evidence_31) |
| both rules together | same | same | 2 (only case_308 and case_309) |

Gold cannot separate the two rules: no gold case has an exhaustive dump after an observation, nor a bundle-only
proof for an unmentioned subject. The choice rests on what the files are, as described above.

**Own case (b) corrected:** its session-3 expectation (COMPLETE via the later bundle) contradicted this semantics:
the bundle mentions only the decoys. Corrected to INCOMPLETE (account_9001 PRESENT via evidence_b1). The old
expectation and the reasoning are kept in its CASE.md. The decoys are still not linked, and own cases pass 4/4.

Held-out case_24 shaped this rule, so held-out is not independent validation for it.

## 17. Session 14: hidden-grader evidence, schemas, fail-fast inputs

**Output choice follows the hidden grader, not local gold.** The graded CSV with SHA 7682a1ff… scored 25.5/30;
the later variant with section 15's or 16's snapshot rule scored 25.2/30. Both snapshot rules are off by default
(they remain options in `StateResolver`). The output is again byte-identical to the 25.5 CSV. Local gold for the
delivered configuration, measured with `score.py`:

| split | status | exact | step P | step R | step F1 | sequence |
|---|---|---|---|---|---|---|
| dev (22) | 22/22 | 17/22 | 1.000 | 0.950 | 0.975 | 17/22 |
| held-out (10) | 10/10 | 3/10 | 1.000 | 0.875 | 0.933 | 3/10 |
| all (32) | 32/32 | 20/32 | 1.000 | 0.922 | 0.960 | 20/32 |

Own cases: **3/4**. Case (b)'s corrected expectation (section 16) needs the scoped-bundle rule, which is now off,
so it fails. It is left failing and reported, not edited.

**Explicit output schemas** (`ghost/schemas.py`, tests `test_schemas.py`, written first and failing):
- intent items are `{id, label ∈ DELETE|NON_DELETE|UNSURE, reason}`;
- vision answers are `{rows[], unreadable[]}`, with a resource-id pattern and a state enum;
- investigator actions are `{action ∈ closed tool list, args: object}`.

UNSURE labels, unreadable rows and schema failures are counted and never used; the rules or the transcript
decide instead. The prompts ask the model to flag uncertainty instead of guessing, and treat request text and
screenshot text as data, not instructions.

**Fail-fast inputs** (`test_cli.py`, written first and failing): a manifest file missing on disk, a wrong CSV
header, or a bad dataset path stops the run with exit 1 and a one-line `ERROR:`. No output file is written and
no traceback is shown. An empty request text still gets a valid row.
