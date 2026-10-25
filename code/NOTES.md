# NOTES — working summary (started from a private strategy draft, not part of this repo)

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
  R 0.835→0.860. Held-out unchanged. In the 518 run it changes 0 rows. Re-measured in session 6: the default run has
  39 activity-derived categories and 0 system fallbacks. With `activity_category=False` those 39 fall back to the
  system default, and 0 rows change.
  Tests: `tests/test_category_activity.py`.
- **Zero-link rule (explicit, `planner.is_zero_link`):** a deletion-authorized request whose linking yields
  no resource at `audit_at` is `COMPLETE` with `[]`. With no evidence there is no finding to cite, so the
  row cannot be INCOMPLETE. No verification step is invented without evidence, and the request does
  authorize deletion, so NOT_APPLICABLE would be wrong. On dev, all 3 zero-link cases have gold COMPLETE.
  ~~Known conflict~~ (superseded in session 3): `validate.py` now reports COMPLETE with no steps as a warning,
  so the 2 zero-link rows are valid (0 invalid). problem_statement.md does not forbid an empty COMPLETE.
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
- **Own cases** (`code/evaluation/own_cases/`, `run_own_cases.py`, `main.py --dataset DIR`): 3/4 pass. **Open finding
  (closed in session 5, negation table; own cases now 4/4):** "Please do not delete my account." is UNKNOWN to the sentence tables, and `effective_intent` maps
  UNKNOWN → DELETE, so the refusal is audited as a deletion (INCOMPLETE). Changes 0 of 518 rows today (0 UNKNOWN there),
  but it fails open on unseen text. Any fix must be re-measured on the 23 unknown sample openings (all deletions).
- **Name channel** (`channels.py` N, diagnostic only): dev 0 gold recovered, 2 extra → precision 0.000. Names stay unused.

## Account finder (2026-10-25, session 4), measured with `compare.py` / scratch measurement
- **Kept, default on (`find_account=True`, `account_finder.py`):** applies only when linking found no account_service
  resource; every sample has exactly 1. Candidates are account DELETE_RECORD rows in [reported_at − 75 min, reported_at + 10 min]
  and ≤ audit_at. Remove accounts with an evidence unit (≤ audit_at, not REFERENCED) carrying any non-subject identifier.
  The user number only breaks a tie among survivors; still ambiguous → nothing. Dev: 5 recovered, 0 wrong, 6 abstained
  (precision 1.000). The strictly-before window (−75/0) gives 2/0/9. Held-out aggregate: 1/0/8.
- **Kept, default on (`table_coverage=True`, `parse_sql`):** a SQL dump without snapshot_scope covers the system of
  each inventory table it holds (any copy suffix). Gold cites such a dump (failover replica + primary profiles) as
  proof of absence. Alone it changes no sample metric; with the finder, dev P 0.973→0.991.
- Final: dev status 1.000, P 0.991, R 0.901, F1 0.944, exact 0.636; held-out F1 0.857, exact 0.000.
  518: 36 rows each gain one account record, no status flips.
- **Rejected:** same-batch for analytics (dev precision 0.400 with a reported_at window; 0 correct when anchored on the
  account delete). Same-batch for audit records is impossible: no worker activity targets security_service.

## Propagation, forced pick, negation (2026-10-25, session 5)
- **Kept, default on (`propagate_accounts=True`):** `account_finder.propagate` runs over every deletion request in
  `dataset/` (518 + 32 samples). An account belongs to one user. Evidence-linked accounts start as taken. Rounds decide
  unresolved requests with the finder rule; a same-round pick of one account by two users is dropped; picks are final.
  Rounds resolve 48, 2 and 1. Dev 5/0 (precision 1.000), unchanged from the plain finder. 518: 9 more rows each gain
  an account (45 found in total). No sample metric changes, so those 9 picks are unvalidated by labels.
- **Forced pick (measured, NOT enabled):** closest delete to reported_at, user number as tie-break. Dev precision 0.400 at
  margin ≥ 0 and 0.500 at best (≥ 2, ≥ 5 or ≥ 10 min); it would touch 287 / 279 / 260 / 169 rows of the 518.
  The gold account is among the candidates in 5/5 dev ambiguous cases, so the remaining gap is choosing between candidates.
  Diagnostics: `python3 code/evaluation/channels.py --accounts`.
- **Negation table (`intent.NEGATIONS`):** an UNKNOWN text containing an explicit refusal of deletion is NON_DELETE (logged).
  The strict classifier is unchanged; other UNKNOWN text still defaults to DELETE (logged). 518 and sample intents are
  unchanged. Own cases now pass 4/4. The open finding from session 3 is closed.

## After the first submission (2026-10-25, session 7)
- First submission: Output CSV 7.2/30, Code zip 4.5/30. Causes found: (1) rows were in string order, while
  `deletion_requests.csv` is numeric, so 0/518 positions matched (fixed: `loaders.case_sort_key`; validate.py
  checks it); (2) no model in an "AI-powered agent" challenge; (3) incomplete answers on unseen cases (held-out 10/10
  cases missed a record).
- **LLM agents (default on, cached):** `ghost/llm.py` is a stdlib OpenRouter client with a SHA-256-keyed response cache in
  `code/llm_cache/`. `--offline` = cache only; `--no-llm` = rules only. The intent agent agrees with the tables on 375/375
  known texts and labels the 23 unknown sample texts correctly (23/23 DELETE). The vision agent matches the transcript on
  5/11 images; all 6 disagreements are model errors (invented identifiers, dropped visible emails, an empty answer), so the
  transcript is used there. Neither agent changes a 518 row. Tests and evaluation scripts are offline: an early test run
  made live calls, which wasted free quota.
- **Ownership from any date (`link_after_audit=True`):** in the samples, the 8 records that only post-audit evidence links
  are all in gold (0 outside). Ownership and category (`category_any_time`) may come from any date; state and citations
  only from evidence <= audit_at. A retained record with no state <= audit_at is a future VERIFY_RECORD_PRESENT with ""
  (INCOMPLETE cases only; `planner.build_steps_unproven`).
- **Explicit absence (`explicit_absence=True`):** a record's own ABSENT observation (404 lookup) stays the citation even
  when a later covering snapshot exists. Gold cites the 404 lookup.
- Final: dev F1 0.953, exact 0.682; held-out F1 0.909, exact 0.100, linkR 0.783; precision unchanged. 518: 152 rows
  gain records (122 audit, 75 account, ...), 0 removed, 0 status flips.
- Rejected again with numbers: batching by time around the case's own linked records puts the gold account closest in
  only 2/11 cases.
- Held-out is no longer clean: its misses were studied in detail in this session.

## Claude agents and the investigator (2026-10-25, session 8)
- Backend: Claude Sonnet via Claude Code headless (`llm.ClaudeCodeClient`). Lean flags: --system-prompt, --tools "",
  --strict-mcp-config with an empty config, --exclude-dynamic-system-prompt-sections, --no-session-persistence, run from
  an empty temp dir. Overhead is about 650 tokens per call (a default call loads about 109k). Images: the Read tool only,
  inside a temp dir holding just the image copy. `--bare` is unusable because it needs ANTHROPIC_API_KEY (OAuth is not read).
- Intent (Claude): 375/375 agree with the tables, 23/23 unknown sample texts correct. Vision (Claude): 10/11 agree; the
  1 disagreement (backup console REF owner) was checked by viewing and the transcript was kept. The agreement rule was
  fixed: identifiers outside identities are fine when the transcript has them too (decoys on screen). Free model: 6/11.
- Investigator: tool-calling loop (JSON actions, 6-turn cap), with merge() guardrails. Pilot on 32 samples: 0 proposals,
  identical metrics, about 15.7k tokens per case. The 518 run routes flagged cases (category conflict 8 / weak link 39 /
  no account 222 = 263) by priority with budget 20: 1 proposal (drop a retained audit record), rejected by the guardrail.
  0 rows change.
- The Pro session limit was hit once during the pilot (resets after 5 h); all calls are cached, so reruns resume.
- Final run: 116 Claude calls, 504,201 tokens, $1.59 API-equivalent (Pro subscription, not billed per token).
