# FINAL SCORE RESULTS (session 14b, 18:11 IST; deadline 19:00)

**Submit `~/Desktop/final_submission_candidate_2/`.** `~/Desktop/final_submission_candidate/` (17:54) is kept
untouched as a fallback. Its output.csv is the same file.

| file | size (B) | SHA-256 |
|---|---|---|
| output.csv | 609,237 | 7682a1ff0bfb7bde4eac7d1efd12aebf473b20b994c642592ccfaea614b5299d (= the CSV the grader scored 25.5) |
| code.zip | 208,037 | 6d5405b47be85b4335140e7b65b44c653e9f2c3722a340bba140f2fa4bb5e5e6 (101 files) |
| log.txt | 125,545 | 73a2b90637a2883f3f1f68c81fbf2528d52062fc8f896640330d4a575334dfdb (chat transcript; 0 key matches) |

## Runs, all byte-identical to the 25.5 CSV
- live AI-enabled `python3 code/main.py` (Claude Code; 75 live Sonnet calls + 39 replayed);
- `--offline` ×2;
- `--no-llm`;
- clean extraction of code.zip (`env -i PATH=/usr/bin:/bin`, no claude, no cache, no keys): default, `--offline`,
  `--no-llm` and a second run.

## Checks
- **Tests:** 166 run, OK in the repo. In the extraction, 166 OK with 4 skipped: 3 need `pdftotext`, which is not
  on the minimal PATH (the committed text fallback is tested); 1 needs `problem_statement.md`, which is not zipped.
- **Validator:** 0 invalid rows; 1 warning (case_63, a COMPLETE row with no steps, because there is no evidence
  to cite).
- **audit_rows invariants:** a, b and c hold on gold; citation = latest mentioning file, 1050/1050.
- **CSV format:** header `case_id,deletion_status,steps_json`; 518 rows in request order; LF only.
- **Statuses:** COMPLETE 152, INCOMPLETE 356, NOT_APPLICABLE 10.
- **Archive:** 0 cache, 0 forbidden entries, 0 secrets; `ghost/schemas.py` and `test_schemas.py` are included.

## AI path (live run)
- **Intent:** 375/375 agree with the tables; 23 unseen texts labelled; 0 UNSURE; 0 schema failures.
- **Vision:** 10/11 agree with the transcript; 1 disagreement, where the transcript was used.
- **Investigator:** 20 reviews; 0 accepted, 2 rejected by `merge()`.
- **Usage:** 489,844 tokens, about $1.60 API-equivalent (Pro plan, not billed per token).

## What changed vs final_submission_candidate
- **code.zip:** schemas, UNSURE/unreadable flags, fail-fast inputs, 10 new tests, updated README and reports.
- **output.csv:** no change.

**Not claimed:** any hidden-grader change. The output score should repeat 25.5 because the file is identical. The
code score can only be known from a new grader result.
