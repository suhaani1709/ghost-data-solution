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
