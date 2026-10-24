# NOTES — working summary (from OCTOBER_STRATEGY.md §2–4)

## Hard output contract
- `output.csv` at repo root: header `case_id,deletion_status,steps_json`; exactly 518 rows, one per `case_id`, sorted by `case_id`.
- `deletion_status` ∈ `COMPLETE | INCOMPLETE | NOT_APPLICABLE`. NOT_APPLICABLE ⇔ request does not authorize deletion, with `steps_json=[]`.
- `steps_json`: valid JSON array, 7 keys per step, `step_no` consecutive from 1, phases FINDING → REMEDIATION → VERIFICATION.
  Inside a phase, sort by operation-table order, then `system_id`, then `resource_id` (matches 32/32 samples).
- Operation ↔ state ↔ phase pairs are fixed (15 operations). Don't invent any.
- COMPLETE ⇒ verification steps only, each citing evidence captured ≤ `audit_at`.
  INCOMPLETE ⇒ findings (cite evidence) + remediation (`""`) + verification of every relevant resource's final state (`""`).
- `evidence_id` ∈ {`file_id`, `activity_id`, `audit_id`}, never captured after `audit_at`.
- Remediation: disable flows and block restores before record changes. ("Downstream before source" is ambiguous; samples follow the plain sort key.)
- Deliverables: `evaluation/evaluation_report.md` + `evaluation/usage_report.md` (write to `code/evaluation/` and mirror to `evaluation/`), README, `log.txt`, agent trace.
- No organizer files, no golden labels, no `case_id` literals, deterministic output.

## Dataset facts (verified)
- Intent: 508 requests use 17 deletion templates (12 EN + PT/ES/FR/JA/KO); exactly **10** non-deletion one-offs. Samples contain **0** NOT_APPLICABLE.
  Keyword regexes misfire ("correct treatment" ≠ correction request). Use a sentence table and send unmatched texts to UNKNOWN.
- 10 `CLASSIFY_REQUEST … non-deletion` activity rows exist (keyed by `account_*`, not by email).
- Identity: every request email resolves to exactly 1 user. 418 match a current email, **100** only a historical one. No email maps to two users.
- `email_hash` = SHA-256(lowercased email). Hashes of **old** emails appear in evidence as `correlation_key`.
- Evidence: 94 files (26 logs, 29 JSON/TXT, 24 SQL dumps, 4 PDFs, 11 PNGs). Explicit `record_type` and state vocabularies appear in several formats.
- Category ≠ system (e.g. analytics `contact_lookup` with `email_opt_in=true` → marketing → DELETE).
- Replica drift is real: a row present in any replica means PRESENT.
- Look-alike decoy emails (33) exist, so match identifiers exactly. No fuzzy matching. OCR corrupts identifiers in images.
- `cache_*` / `email_delivery_*` exist only as activity claims; samples never cite them.
- `reported_status` is not proof (reported COMPLETE → actually INCOMPLETE in 11/17 samples).

## Identity & temporal model
- `IdentitySet(user)` = user_id + current name/email/phone/email_hash ∪ every old/new value in `user_audit_log` ∪ sha256 of every email.
  Emails are lowercased; phones are matched verbatim. Exact token matching only.
- Linkage graph over `(system_id, resource_id)`. An evidence unit that co-mentions a resource and an identifier links them. Linkage is sticky once established ≤ `audit_at`.
- State at `audit_at` = state in the latest file with `captured_at ≤ audit_at` that mentions the resource.
  Absence = NOT_FOUND/404/0 rows, or a covering snapshot that lacks the row (cite that snapshot).
- Activity rows only nominate resources. They never set state.

## Build order (this repo)
1. loaders + identity + intent ← **done in `code/ghost/`**
2. evidence parsers → 3. linkage → 4. policy mapping → 5. state at audit_at → 6. steps + serializer → 7. validator/scorer vs samples.

## Linking improvements (2026-10-24), measured with `code/evaluation/compare.py`
- **Reference following (kept, default on):** one hop, only from already-linked resources, evidence ≤ `audit_at`.
  Channels: REFERENCED rows of a linked unit (`referenced_by` column, e.g. `source_resource_id`) and activity rows
  "repopulated downstream resource X" whose `resource_id` is linked. Dev: +1 recovered, 0 extra, linkP 0.980.
  The activity channel fired on no dev case.
- **Images (kept, default on):** `code/image_transcripts.md` (hand transcript of the 11 PNGs, validated against
  identities and prefix patterns by `code/ghost/parse_images.py`) → observations with `file_kind=image`.
  No change on the samples. In the 518-case run, invalid rows went from 9 to 2 and 9 rows changed.
- **Resource-number fallback for zero-link cases (rejected, removed):** it touched 3 dev cases, added 1 wrong
  resource (dev step P 0.951→0.942) and touched 0 of the 518. It was not kept.

## State / policy / zero-link rules (2026-10-24, session 2), measured with `compare.py`
- **Replica drift persistence (kept, default `replica_persist="drift"`, `state.py`):** "any copy present"
  already held within one file and across files of the same `captured_at`. The dev failure was different:
  a primary-only inventory snapshot (snapshot_scope, 0 rows) captured *later* proved ABSENT and overrode
  an earlier file whose failover-replica table still held the row while its primary table did not.
  Rule: if the latest replica capture of the system (≤ `audit_at`) holds the resource exposed in a replica
  copy while that file's primary copy lacks it or holds it compliant, the resource stays PRESENT, cited to
  that file, until a later replica capture shows it gone or compliant. `"any"` (no primary condition) scored
  the same on the samples; `"drift"` is stricter. Dev status 0.955→1.000, P 0.951→0.962, R 0.810→0.835.
  Held-out unchanged. 0 of 518 rows changed. Tests: `tests/test_replica_drift.py`.
- **Activity treatment as category fallback (kept, `activity_category=True`):** used only when no observation
  carries a category hint. A DELETE_RECORD / REDACT_RECORD / ANONYMIZE_RECORD activity row on the resource
  (≤ `audit_at`, result ignored) picks the one category the system is seen to hold with that rule action.
  On dev, this operation matched the gold treatment for all 46 resources that had one, with no conflicts.
  Fixes support_platform without a hint (SUPPORT_MESSAGE→SUPPORT_ATTACHMENT). Dev P 0.962→0.990,
  R 0.835→0.860. Held-out unchanged. The 518 run has 0 category fallbacks, so 0 rows change.
  Tests: `tests/test_category_activity.py`.
- **Zero-link rule (explicit, `planner.is_zero_link`):** a deletion-authorized request whose linking yields
  no resource at `audit_at` is `COMPLETE` with `[]`. With no evidence there is no finding to cite, so the
  row cannot be INCOMPLETE. No verification step is invented without evidence, and the request does
  authorize deletion, so NOT_APPLICABLE would be wrong. On dev, all 3 zero-link cases have gold COMPLETE.
  **Known conflict:** `validate.py` flags COMPLETE with no steps, so the 2 zero-link rows in the 518 output stay
  "invalid" under our own validator. problem_statement.md does not forbid an empty COMPLETE.
  Rejected alternatives: (a) resource-number convention. Evidence rows contradict it in 38 of 45 account/user
  pairs. (b) LINK_RESOURCE_IDENTITY data-catalog activity claims. On dev, 2 such claims dated ≤ `audit_at`
  are not in gold. For the zero-link cases, one claim has no evidence behind it and the other is contradicted
  by an image showing a different person. Tests: `tests/test_zero_link.py`.
- **Runtime dependency (resolved in session 3):** `parse_pdf.py` calls the `pdftotext` binary (poppler).

## Packaging / robustness (2026-10-24, session 3)
- **Validator:** COMPLETE with `[]` is now a *warning* in `validate.py` (problem_statement.md allows it; zero-link
  rule). INCOMPLETE with `[]` is still an error. Final output: VALID, 0 invalid rows, 2 warnings. Tests: `tests/test_validate.py`.
- **PDF fallback:** if `pdftotext` is not on PATH, `parse_common.pdf_pages` reads `code/pdf_text/<file_id>.md` (the
  committed `pdftotext -layout` pages, exact round trip) and logs one WARNING per PDF. `main.py` now logs at WARNING.
  `output.csv` is byte-identical with and without pdftotext (`tests/test_pdf_fallback.py`, end-to-end with PATH=/usr/bin:/bin).
  Regenerate: `python3 code/ghost/parse_pdf.py --write-text`.
- **Own cases** (`code/evaluation/own_cases/`, `run_own_cases.py`, `main.py --dataset DIR`): 3/4 pass. **Open finding,
  not fixed:** "Please do not delete my account." is UNKNOWN to the sentence tables, and `effective_intent` maps
  UNKNOWN → DELETE, so the refusal is audited as a deletion (INCOMPLETE). Changes 0 of 518 rows today (0 UNKNOWN there),
  but it fails open on unseen text. Any fix must be re-measured on the 23 unknown sample openings (all deletions).
- **Name channel** (`channels.py` N, diagnostic only): dev 0 gold recovered, 2 extra → precision 0.000. Names stay unused.

## Session 4 (2026-10-25): late-export linking, intent fallback
- **Baseline re-measured** before any change: identical to the session-3 report (dev exact 0.409, R 0.860;
  held-out exact 0.000, R 0.736; 92 tests OK; output.csv byte-identical to the committed one).
- **Late-export linking (kept, default `late_kinds=("log","json","sql","txt")`):** a unit whose own
  event_time is <= audit_at links even if its file was captured after audit_at (central log exports,
  service record exports). It is never cited. The resource is added only when compliant, and only to an
  INCOMPLETE case, as a future verification with evidence_id "". So it cannot change a status or put
  a late file id in a finding. Non-compliant late resources are skipped and counted
  (`late_noncompliant_skipped`); a finding would need a citation. In a COMPLETE case, late resources
  are omitted: a COMPLETE step must cite on-time evidence. Dev R 0.860→0.876, exact 0.409→0.455,
  0 extra. Held-out R 0.736→0.792 (records part; prompted by an aggregate held-out diagnostic, so not
  independent). 518 run: +167 steps in 116 rows, 0 status changes. Tests: `tests/test_late_links.py`,
  own cases e/f.
- **Intent cue fallback (kept):** UNKNOWN texts go to `intent.infer_unknown`: refusal → NON_DELETE,
  deletion cue → DELETE, non-deletion request cue → NON_DELETE, no cue → DELETE. The tables still win.
  23/23 unseen sample texts → DELETE. As an independent classifier it reproduces all 518 hand labels.
  Fixes own case (a); adds case (g) (Spanish). 0 output rows change. Tests: `tests/test_intent_fallback.py`.
- **Measured and rejected:** primary-account DELETE_RECORD rows near `reported_at`. The signal is real
  (0–70 min before it on all dev cases), but the worker interleaves requests: precision 0.32 / 0.64 / 0.71
  for −75/+10, −30/+10 and ±5 min windows. The zero-padded `account_00N`↔`user_0N` convention is a
  sample artefact (3/517 eval users have two-digit ids).
- **Remaining dev misses (15):** 9 deleted primary accounts known only from an activity row, 3 analytics
  profiles with every identifier nulled, 2 audit records absent from all participant files, 1 absent
  account. None has an exact identifier path left.
