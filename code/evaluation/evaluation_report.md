# Evaluation report: Ghost Data Still Exists deletion-audit agent

Every number below comes from running the scripts named next to it on the final code
(session 4, 2026-10-25, on top of commit `b039e88`). Nothing is estimated.
Section 11 compares the session-4 final with the session-3 baseline, re-measured on 2026-10-25,
on the same splits.
Where a number is plain arithmetic on measured counts (for example a ceiling), the arithmetic is shown.

Reproduce:

```bash
python3 code/evaluation/score.py              # sections 1-3
python3 code/evaluation/compare.py base follow_refs images follow+images replica_any replica_drift drift+actcat late_log late_records
python3 code/evaluation/breakdown.py          # section 6
python3 code/evaluation/channels.py           # section 7
python3 code/evaluation/run_own_cases.py      # section 5
python3 code/evaluation/validate.py output.csv
```

**Splits.** The 32 public samples (`dataset/sample_output.csv`) are the only labelled data.
`score.py` sorts them by `case_id`: the first 22 are **dev** and the last 10 are **held-out**.
Held-out cases were looked at only in aggregate. Section 4 says which rules came from dev.

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
| all | 32 | **1.000** (32/32) | 0.312 |
| dev | 22 | **1.000** | 0.455 |
| held-out | 10 | **1.000** | 0.000 |

Status confusion (all 32, `breakdown.py`): COMPLETE 10→10, INCOMPLETE 22→22, NOT_APPLICABLE 0
(the samples contain no non-deletion request).

## 2. Step-level and field-level accuracy

| split | step P | step R | step F1 |
|---|---|---|---|
| all | 0.994 | 0.845 | 0.913 |
| dev | 0.991 | 0.876 | 0.930 |
| held-out | 1.000 | 0.792 | 0.884 |

Field accuracy (position-aligned):

| split | step_no | phase | system_id | resource_id | operation | state | evidence_id |
|---|---|---|---|---|---|---|---|
| all | 0.84 | 0.83 | 0.60 | 0.60 | 0.64 | 0.65 | 0.84 |
| dev | 0.88 | 0.88 | 0.75 | 0.75 | 0.80 | 0.80 | 0.88 |
| held-out | 0.79 | 0.75 | 0.35 | 0.35 | 0.38 | 0.40 | 0.78 |

Precision is near 1, so emitted steps are almost always right. The loss is recall: missing
resources (section 6). Because field accuracy is position-aligned, one missing resource early in the
sort order shifts every later step. That is why held-out system/resource accuracy (0.35) is much
lower than its step recall (0.792).

## 3. Sequence accuracy

| split | sequence accuracy |
|---|---|
| all | 0.312 |
| dev | 0.455 |
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
| Late-export linking, logs (session 4) | a **dev** failure (case_09): log events before audit_at in a file exported after it | measured: no held-out change |
| Late-export linking, JSON/SQL/TXT records (session 4) | the same rule applied to every parser whose units carry a per-record timestamp; **prompted by an aggregate held-out diagnostic** (counts by system / file kind, no case ids) | **not independent**: held-out R 0.736→0.792 is partly in-sample for this rule. Dev: 0 extra resources |
| Intent cue fallback (session 4) | contract §6.5; checked against the 23 unseen sample openings (all deletions) and the 518 hand labels | no sample is NOT_APPLICABLE; 0 of 518 rows change |

Up to session 3, no dev-derived rule changed a held-out metric (section 9). In session 4 the
late-export rule raised held-out recall. The log-only form came from dev and did not move held-out.
The extension to record files was chosen after an aggregate held-out diagnostic showed JSON records
of the same shape. The held-out gain is therefore reported, but it is not a clean out-of-sample number.
Planner conventions were informed by every sample, as before.

## 5. Own evaluation cases (7 cases, built by us)

Each case is a directory under `code/evaluation/own_cases/<name>/` with its own `dataset/` in the
real schema (fictional people, `example.com` / `example.org` addresses, `+1 555 01xx` phones),
an `expected_output.csv`, and a `CASE.md` with the derivation. **The expected answer was derived by hand
from the rules and written down before the pipeline was run on the case.** `dataset/` was not edited.
`make_fixtures.py` regenerates the files. Run: `python3 code/evaluation/run_own_cases.py`.

| case | what it tests | expected (hand-derived) | pipeline | result |
|---|---|---|---|---|
| a_do_not_delete | "Please do not delete my account. I still use it every week." with a live profile row in evidence | `NOT_APPLICABLE`, `[]` | identical (session 3: `INCOMPLETE`, 3 steps) | **PASS** (was FAIL) |
| b_lookalike_decoy | the real profile is deleted (empty covering snapshot); same-name search doc with `ada.quill@exarnple.com`; analytics row with SHA-256 of `ada.quil@example.com` | `COMPLETE`, 1 step: VERIFY_RECORD_ABSENT account_9001 cited to evidence_b2 | identical | **PASS** |
| c_replica_holds_row | primary table lacks the row, failover replica table holds it; activity claims DELETE SUCCESS | `INCOMPLETE`: REPORT_REMAINING_RECORD (evidence_c1) → DELETE_RECORD → VERIFY_RECORD_ABSENT | identical | **PASS** |
| d_old_email_hash_only | request uses a historical email (audit log); the only evidence is a search hit whose `correlation_key` is SHA-256 of that old email | `INCOMPLETE`: REPORT_REMAINING_RECORD search_9301 (evidence_d1) → DELETE_RECORD → VERIFY_RECORD_ABSENT | identical | **PASS** |
| e_late_export_incomplete | exposed search entry on time; a log **exported after audit_at** whose trace (08:50, before audit_at) reads a retained `audit_record` for `subject_ref=user`; a second trace after audit_at looks up the email (account 404) | `INCOMPLETE`: report / delete / verify search_9401, plus VERIFY_RECORD_PRESENT audit_record_9402 with `""`; the post-audit account is not reported | identical | **PASS** (session-3 code: FAIL, audit record missing) |
| f_late_export_complete | same late log; the search entry is already gone on time | `COMPLETE`: VERIFY_RECORD_ABSENT search_9401 (evidence_f2). The audit record is **omitted**, because a COMPLETE step must cite evidence captured ≤ audit_at | identical | **PASS** |
| g_spanish_refusal | "Por favor, no eliminen mi cuenta. Todavía la uso para mis pedidos." with a live profile | `NOT_APPLICABLE`, `[]` | identical | **PASS** (session-3 code: FAIL) |

**7 of 7 pass.** Run with the session-3 code, (a), (e) and (g) fail, so the new cases do detect
the old behaviour.

**Finding from case (a), fixed in session 4** (history kept below). The intent classifier accepts a text only if every sentence is in
its tables. "Please do not delete my account." is not in them, so the text is `UNKNOWN`, and
`intent.effective_intent` maps `UNKNOWN` to `DELETE`, logging the warning
`intent UNKNOWN, defaulting to DELETE`. The refusal is then audited as a deletion. This default was chosen because all 518
evaluation texts are covered by the tables (0 UNKNOWN), and all 32 samples are deletions even though 23
distinct sample openings are not in the tables (score.py prints a warning for each). On the
evaluation set the default changes nothing. On unseen text it fails open toward deletion, which is
the unsafe direction for a "do not delete" request. Possible fixes, all untested: default UNKNOWN to
NOT_APPLICABLE when the text contains a negated deletion verb, or route UNKNOWN texts to review.
Either one would need re-measuring on the 23 unknown sample openings, which are all deletions.

*Session 4 fix:* `intent.infer_unknown()` runs only for texts the tables do not cover. In order:
(1) a refusal of deletion in request form gives NON_DELETE. This covers imperative negation of a
base verb ("do not delete", "don't close"), "not asking/requesting ... deletion", "not a request to
erase", "without removing", "keep my account", "still use it", and es/pt/fr/ja/ko forms. Past-tense
reports such as "I don't think it was deleted" deliberately do not match. (2) A deletion cue outside
a marketing-only clause gives DELETE. (3) A non-deletion request cue (opt-out, correction, copy/export,
login help) gives NON_DELETE. (4) A text with no cue stays DELETE, because the intake is the deletion
channel. Checks: all 23 unseen sample texts give DELETE. Used as an independent classifier on all 518
evaluation texts, the fallback reproduces every hand label, including the 10 non-deletions. Two
disagreements found on the way ("without removing", "not a request to erase") became general
patterns. 25 synthetic texts are in `tests/test_intent_fallback.py`. 0 of the 518 output rows change.

## 6. Failure analysis

**Linking is the bottleneck** (`breakdown.py`, `channels.py`):

| split | gold resources | linked gold | linkage recall | linkage precision | gold only in activity rows | ceiling for evidence linking |
|---|---|---|---|---|---|---|
| dev | 65 | 50 | 0.769 | 0.980 (50/51) | 13 | (65−13)/65 = 0.800 |
| held-out | 46 | 33 | 0.717 | 1.000 (33/33) | 9 | (46−9)/46 = 0.804 |

(Session 3: dev 48/65 = 0.738, held-out 29/46 = 0.630.) Linked = evidence links plus late links used
in INCOMPLETE cases. Dev failure types (`breakdown.py`): 11 × gold resource not in any parsed text
evidence dated ≤ audit_at, 4 × in evidence but no identifier match, 1 × extra resource linked.

**Session-4 diagnosis of the remaining dev misses** (15 resources). 9 are `account_service` primary
profiles already ABSENT: they appear only in a `DELETE_RECORD … primary profile account_N` activity
row, with no identifier. 3 are ANONYMIZED analytics profiles whose every observation has all
identifiers nulled. 2 are retained `security_service` audit records that appear in no participant
file at all. 1 is an absent account. None of these has an exact identifier path left.

Why there is a recall ceiling:
1. **Activity rows have no person column.** `system_activity.csv` has 8 columns (`activity_id,
   event_time, event_type, source_system, target_system, resource_id, reported_result, details`). Except
   for the 12 `LINK_RESOURCE_IDENTITY` rows, `details` carries only resource ids. A gold resource that
   appears only in activity rows (13 dev, 9 held-out) cannot be tied to the requester by an exact
   identifier. The only links left are time windows, id numbers or names, and section 7 shows each of
   those is far too imprecise.
2. **Nulled identifiers.** The 4 dev resources that are in evidence but unmatched are compliant
   records: 3 ANONYMIZED and 1 ABSENT. Their observations dated ≤ audit_at carry **0** identifier
   tokens. The deletion workflow removed exactly the
   tokens we would link on. One such resource was recovered by reference following: it is named as
   `source_resource_id` inside a linked record. The rest have no exact link left.

Other known failures:
- Case (a) above: intent failed open on unseen text (fixed in session 4).
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

| E (session 4): `account_service` DELETE_RECORD rows near the case's `reported_at` (the workflow's own report time) | window −75/+10 min: 31 of 32 sample primary accounts found (tp), 66 wrong (fp) | | 0.320 | | | — |
| E′: same, −30/+10 min | tp 7, fp 4 | | 0.636 | | | — |
| E″: same, ±5 min | tp 5, fp 2 | | 0.714 | | | — |

E was measured on all 32 samples as a diagnostic, and the precision column is tp/(tp+fp). The
primary-account row of every dev case sits 0–70 min before `reported_at`, which is a real signal.
But the deletion worker interleaves many requests (two dev cases share the same `reported_at`), so
every window either misses most accounts or adds wrong ones. Rejected (bar: 0.95).
The resource-number convention (`account_00N` ↔ `user_0N`) holds for the zero-padded legacy sample
users, but only 3 of the 517 evaluation users have two-digit ids. It was not pursued as a rule
because it would fit sample artefacts.

Also rejected:
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

| commit | change | dev status | dev F1 | dev exact | held F1 | held exact | empty COMPLETE (518) | rows differing from final |
|---|---|---|---|---|---|---|---|---|
| c7f13b5 | baseline v0 | 0.955 | 0.870 | 0.318 | 0.848 | 0.000 | 9 | 9 |
| db6dfba | absence proof, channel diagnostics | 0.955 | 0.870 | 0.318 | 0.848 | 0.000 | 9 | 9 |
| ea71021 | linking diagnostics | 0.955 | 0.870 | 0.318 | 0.848 | 0.000 | 9 | 9 |
| 84c14b9 | reference following, image evidence | 0.955 | 0.875 | 0.364 | 0.848 | 0.000 | 2 | 0 |
| ce57f8e | images, reference following | 0.955 | 0.875 | 0.364 | 0.848 | 0.000 | 2 | 0 |
| 84fe0de | replica drift, activity category, zero-link rule | **1.000** | **0.920** | **0.409** | 0.848 | 0.000 | 2 | 0 |
| b039e88 (session 3) | validator warning, PDF fallback, own cases, docs | 1.000 | 0.920 | 0.409 | 0.848 | 0.000 | 2 (warnings) | 116 |
| session 4 | late-export linking, intent cue fallback | 1.000 | **0.930** | **0.455** | **0.884** | 0.000 | 2 (warnings) | 0 |

**Per option** (`compare.py`, final code with options toggled):

| config | dev status | dev P | dev R | dev F1 | dev exact | dev linkR | dev linkP | recovered / extra vs base |
|---|---|---|---|---|---|---|---|---|
| base | 0.955 | 0.951 | 0.802 | 0.870 | 0.318 | 0.723 | 0.979 | — |
| + follow_refs | 0.955 | 0.951 | 0.810 | 0.875 | 0.364 | 0.738 | 0.980 | 1 / 0 |
| + images only | 0.955 | 0.951 | 0.802 | 0.870 | 0.318 | 0.723 | 0.979 | 0 / 0 |
| follow + images | 0.955 | 0.951 | 0.810 | 0.875 | 0.364 | 0.738 | 0.980 | 1 / 0 |
| + replica_any | 1.000 | 0.962 | 0.835 | 0.894 | 0.409 | 0.738 | 0.980 | 1 / 0 |
| + replica_drift | 1.000 | 0.962 | 0.835 | 0.894 | 0.409 | 0.738 | 0.980 | 1 / 0 |
| + activity category (session 3 final) | 1.000 | 0.990 | 0.860 | 0.920 | 0.409 | 0.738 | 0.980 | 1 / 0 |
| + late links, logs | 1.000 | 0.991 | 0.876 | 0.930 | 0.455 | 0.769 | 0.980 | 3 / 0 |
| **+ late links, logs + records (session 4 final)** | **1.000** | **0.991** | **0.876** | **0.930** | **0.455** | 0.769 | 0.980 | 3 / 0 |

Held-out is identical in every config up to "late links, logs": status 1.000, P 1.000, R 0.736,
F1 0.848, exact 0.000, linkR 0.630, linkP 1.000. With "logs + records", held-out is status 1.000,
P 1.000, R 0.792, F1 0.884, exact 0.000, linkR 0.717, linkP 1.000 (4 recovered, 0 extra). This
number is not fully independent (section 4). The planner oracle is 4/4 in every config, and
`invalid_518` is 0 in every config.
Images change no sample score. In the 518-case run, the final config with `images=False` has 9
empty-COMPLETE rows and with `images=True` it has 2. At commit level, 9 rows changed (commit table).

**Session 3:**
- `validate.py`: COMPLETE with `[]` is now a warning. On the final `output.csv`: **VALID, 0 invalid rows, 2 warnings**.
- PDF fallback: with `pdftotext` removed from PATH, `output.csv` is byte-identical (`cmp`), and 4 warnings are logged.
- Own cases: 3/4 pass. The failure is reported in section 5 and not fixed.
- Test suite: 92 tests, all pass (`python3 -m unittest discover -s code/tests`).
- `code.zip` check: unpacked into an empty directory with `dataset/` linked in, `main.py` reproduces the root
  `output.csv` byte for byte. The suite passes there too (92 tests, 1 skipped). The planner-oracle table test now skips
  when `problem_statement.md` is absent, because the documented zip command does not include that file.

## 10. Final 518-case output checks

`python3 code/main.py`: INCOMPLETE 356, COMPLETE 152, NOT_APPLICABLE 10 (unchanged from session 3).
Total steps 2858 (session 3: 2691). Late resources added: 167 steps in 116 rows: 116
VERIFY_RECORD_PRESENT security_service, 49 VERIFY_RECORD_ABSENT account_service, 2
VERIFY_RECORD_PRESENT legal_service, all with `evidence_id` "". 2 late resources were skipped
because they were non-compliant and a finding would need a citation. 0 statuses changed. Category
fallbacks 0, state coercions 0. `validate.py`: VALID, 0 invalid rows, 2 warnings (zero-link COMPLETE
`[]`). Two runs are byte-identical, and so are runs with and without pdftotext. Runtime 1.6 s,
peak RSS 140 MB (`/usr/bin/time -l`, Apple Silicon laptop).

## 11. Session 4: baseline vs final (same splits, both re-measured 2026-10-25)

| metric | split | session-3 baseline | session-4 final |
|---|---|---|---|
| status accuracy | dev / held-out | 1.000 / 1.000 | 1.000 / 1.000 |
| exact case | dev / held-out | 0.409 / 0.000 | **0.455** / 0.000 |
| step precision | dev / held-out | 0.990 / 1.000 | 0.991 / 1.000 |
| step recall | dev / held-out | 0.860 / 0.736 | **0.876 / 0.792** |
| step F1 | dev / held-out | 0.920 / 0.848 | **0.930 / 0.884** |
| sequence accuracy | dev / held-out | 0.409 / 0.000 | **0.455** / 0.000 |
| linkage recall | dev / held-out | 0.738 / 0.630 | **0.769 / 0.717** |
| linkage precision | dev / held-out | 0.980 / 1.000 | 0.980 / 1.000 |
| field acc. evidence_id | dev / held-out | 0.86 / 0.72 | 0.88 / 0.78 |
| own cases | — | 3/4 (a fails) | **7/7** |
| unit tests | — | 92 OK | **103 OK** |
| 518 output | — | VALID, 2691 steps | VALID, 2858 steps, 0 status changes |

**Failures addressed.**
1. *Late-exported evidence was discarded.* The linker kept only files with `captured_at ≤ audit_at`.
   Central log exports and service record exports are often captured a day or two after the audit,
   yet they hold events (a trace with `subject_ref=user_N` then `audit_record_read_completed rows=1`,
   or a profile lookup with the user's email that returns 404) timestamped before audit_at. Those
   facts existed at audit time, but the file cannot be cited. Fix: `Linker.late_links` and
   `StateResolver.resolve_late` use a unit's own event_time. `Pipeline._late_resources` adds such a
   resource only when it is already compliant and the case is INCOMPLETE. Its step is then a future
   verification with `evidence_id` "", so no late file is ever cited and no status can change.
   Tests: `tests/test_late_links.py`, own cases (e) and (f).
2. *Unknown request wording failed open toward deletion.* Fixed by the cue fallback (section 5).
   Tests: `tests/test_intent_fallback.py`, own cases (a) and (g).

**Regressions:** none measured. Dev precision 0.990→0.991, held-out precision 1.000. No resource
was lost in any split ("lost=0" in `compare.py`). 0 of 518 statuses changed.
