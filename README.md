# HackerRank Orchestrate - October 2026

## Ghost Data Still Exists

Build an AI agent that audits whether a user's personal data was actually deleted.

A deletion workflow may report **Complete** while data still exists in databases, logs, support attachments, exports, search indexes, archives, or backups. Sync and restore processes may also bring deleted data back.

For each request, the agent must first determine whether deletion was actually requested. It then returns `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`, reports any remaining data or recreation risk, and produces the ordered remediation and verification steps required to finish an authorized deletion safely.

Read [`problem_statement.md`](./problem_statement.md) for the complete challenge contract.

---

## Solution: setup and run

The deletion-audit agent is a Python pipeline in `code/`: a deterministic evidence engine, plus three
LLM agents for the parts that need judgment. Code audits every model output before it can reach `output.csv`.

- **Intent agent** (`code/ghost/intent_agent.py`): an LLM reads every request text, in any language, in
  batches. The sentence tables cross-check it, and an explicit "do not delete" always wins.
- **Vision agent** (`code/ghost/vision_agent.py`): the LLM opens each PNG screenshot and transcribes its
  records. The reading is used when it matches the development transcript; otherwise the transcript is used
  and the difference is reported.
- **Investigator agent** (`code/ghost/investigator.py`): a tool-calling loop. For each routed case, Claude
  reviews the engine's answer with read-only tools (`record_history`, `search_identifier`, `read_evidence`,
  `account_candidates`, `policy`) and submits corrections. `merge()` applies only proposals that a
  deterministic check backs. Routing sends the cases the engine flags as uncertain (category conflict →
  weak link → no account), up to `--investigate-budget` (default 20). The routed set is computed from those
  flags on every run; no case ids are stored anywhere.
- **Output schemas** (`code/ghost/schemas.py`): every structured model answer is validated against an
  explicit JSON schema before use (`INTENT_ITEM`, `VISION_ANSWER`, `INVESTIGATOR_ACTION`). A model that is
  unsure can say so: intent label `UNSURE`, or a screenshot row listed as `unreadable`. Those answers, and any
  answer that fails its schema, are counted and never used; the rules or the transcript decide instead.
  Tests: `code/tests/test_schemas.py`.
- **Deterministic engine:** identity resolution (current + historical emails, SHA-256 hashes), evidence
  parsing (SQL, JSON, logs, PDF, images), linking, the account finder, state at `audit_at`,
  `deletion_rules.csv` policy, and step planning.

**Models.**
- Default: Claude Sonnet through **Claude Code's headless mode** (`claude -p`, `llm.ClaudeCodeClient`).
  Each call replaces Claude Code's system prompt and loads no tools, MCP servers or project files, so the
  model sees only what the pipeline sends.
- Alternative: free OpenRouter models (`--backend openrouter`, `llm.Client`).
- Answers are cached locally in `code/llm_cache/` during development. **The cache is not shipped in
  `code.zip`** (AGENTS.md §6.9). Without Claude Code, or with `--offline`, the agents make no model call
  and the deterministic rules decide. That reproduces the submitted `output.csv` byte for byte, because the
  agents changed no output row (measured: section 13 of the evaluation report).
- Token use is in `code/evaluation/usage_report.md`.

```text
code/main.py            entry point: agents -> identity -> linking -> state -> policy -> steps
code/ghost/             loaders, identity, intent tables + agent, vision agent, investigator, schemas, llm clients, parsers, linker, state, planner
code/llm_cache/         local cache of model answers + usage_log.jsonl (NOT shipped in code.zip)
code/image_transcripts.md   hand transcript of the 11 PNG screenshots (read at run time; no OCR)
code/pdf_text/          committed `pdftotext -layout` text of the 4 PDFs (fallback, see below)
code/tests/             unit tests (synthetic frames) + sample oracle tests
code/evaluation/        scorer, validator, diagnostics, own test cases, evaluation and usage reports
code/NOTES.md           working notes: every rule, its evidence and its measured effect
```

### Setup

- Python 3 (developed and tested only on 3.13.13) and **pandas** (tested on 3.0.2). Nothing else from pip; the
  rest is the standard library (`sqlite3`, `json`, `csv`, `hashlib`, `re`, `subprocess`).

  ```bash
  python3 -m pip install pandas
  ```

- **Model access (optional):** nothing is needed to reproduce `output.csv`. Without Claude Code the run prints
  a NOTE, makes no model call and uses the deterministic rules. To let the agents call a model:
  - default backend: install Claude Code and log in (`claude` on `PATH`);
  - `--backend openrouter`: set `OPENROUTER_API_KEY` in the environment or in an uncommitted repo-root `.env`
    file (listed in `.gitignore`).

  Without a cached answer and without model access, the agents fall back to the deterministic rules and log
  a warning.

- **Optional:** `pdftotext` from poppler (`brew install poppler`, `apt-get install poppler-utils`).
  If it is on `PATH`, the four PDFs are read with `pdftotext -layout`. If it is missing, the run does
  not fail. Each PDF is read from the committed `code/pdf_text/<file_id>.md` instead, and one line per
  PDF is logged: `WARNING ghost.parse_common: pdftotext not found; using committed text ...`.
  Both paths produce a byte-identical `output.csv` (tested in `code/tests/test_pdf_fallback.py`).
  To regenerate the committed text after a dataset change, run `python3 code/ghost/parse_pdf.py --write-text`
  (this needs pdftotext).

### Run

From the repository root, with `dataset/` in place:

```bash
python3 code/main.py
```

This writes **`output.csv` at the repository root**: 518 rows in the numeric `case_id` order of
`dataset/deletion_requests.csv` (case_33, case_34, …, case_550), with header
`case_id,deletion_status,steps_json`. With the cache in place the run makes no network call, takes a few
seconds, and repeated runs are byte-identical. Other modes:

```bash
python3 code/main.py --offline                                  # cached model answers only, never call the API
python3 code/main.py --no-llm                                   # deterministic rules only (no agents)
python3 code/main.py --investigate-budget 50                    # investigate up to 50 flagged cases
python3 code/main.py --backend openrouter                       # free OpenRouter models for intent/vision
python3 code/main.py --sample --out /tmp/sample_pred.csv        # the 32 public sample requests
python3 code/main.py --dataset DIR --out /tmp/pred.csv          # any directory with the dataset/ schema
```

### Tests and evaluation

```bash
python3 -m unittest discover -s code/tests                      # all unit + oracle tests (offline, no API calls)
python3 code/evaluation/validate.py output.csv                  # output contract check (exit 0 = valid)
python3 code/evaluation/score.py                                # status / step / field / sequence accuracy on the 32 samples
python3 code/evaluation/compare.py base follow_refs images follow+images replica_any replica_drift drift+actcat account table_cover account+cover propagate after_audit explicit_absence after+explicit llm
python3 code/evaluation/breakdown.py                            # failure breakdown (linking recall/precision)
python3 code/evaluation/channels.py                             # rejected linking channels and their precision
python3 code/evaluation/channels.py --accounts                  # account finder / propagation / forced-pick diagnostics
python3 code/evaluation/run_own_cases.py                        # the hand-built cases in code/evaluation/own_cases/
python3 code/evaluation/run_investigator.py                     # investigator on the 32 samples, scored per proposal kind
python3 code/evaluation/audit_rows.py                           # gold-derived invariants checked on all 518 rows
python3 code/evaluation/independent_check.py 40                 # raw-text re-derivation of linked records, diffed
python3 code/evaluation/account_backtest.py                     # account assignment backtest (hidden labelled accounts)
```

`score.py` reports the first 22 samples (by `case_id`) as **dev** and the last 10 as **held-out**.
Results, failures and what was tried are in `code/evaluation/evaluation_report.md`. The same reports
are mirrored to `evaluation/` because `problem_statement.md` and `AGENTS.md` name that path.

### Package

```bash
zip -r code.zip README.md code evaluation -x "code/llm_cache/*" "*/__pycache__/*" "*/.venv/*" "*/venv/*" "*/node_modules/*" "*/.git/*" "*/.DS_Store"
```

This is the command from "Packaging `code.zip`" below, with `evaluation` added as that section allows
for a top-level `evaluation/` directory.
Delete any old `code.zip` first (`rm -f code.zip`): `zip -r` adds and updates entries but never removes
files that no longer exist.

---

## Quick Start

Clone the repository and move into the project directory:

```bash
git clone https://github.com/interviewstreet/hackerrank-orchestrate-october26.git
cd hackerrank-orchestrate-october26
```

Start your AI coding tool from the **repository root** so it automatically reads [`AGENTS.md`](./AGENTS.md) and logs your session turns to `log.txt` in the root directory.

Build your solution in `code/main.py`, or use another language and document its setup and run command clearly in your README.

Your solution must:

- Read the input files from `dataset/`
- Generate one prediction row for every request in `dataset/deletion_requests.csv`
- Write the final predictions to `output.csv` in the repository root

Run the starter Python entry point with:

```bash
python3 code/main.py
```

The blank template at `dataset/output.csv` is provided as a reference. Your final generated file for submission must be the root-level `output.csv`.


## Dataset

All participant-facing files are in `dataset/`:

| File | Contents |
| --- | --- |
| `deletion_requests.csv` | 518 requests |
| `sample_deletion_requests.csv` | 32 sample requests |
| `sample_output.csv` | Correct sample answers |
| `user_identities.csv` | Current user identities |
| `user_audit_log.csv` | Historical identity changes |
| `system_activity.csv` | Activity across services and data processes |
| `deletion_rules.csv` | Required treatment for each data category |
| `evidence_files.csv` | Manifest of supplied evidence files |
| `output.csv` | Blank output template |

Evidence is stored under `dataset/evidence/` and may include PDFs, images, logs, JSON, plain text, or SQL snapshot exports. SQL captures may contain a primary database, regional replicas, a reporting replica, or a failover replica so replication drift can be investigated directly. The `.sql` files are readable as text and executable with SQLite.

Only `deletion_requests.csv` requires answers. The other files provide evidence and context.

---

## Output

Create `output.csv` with these columns in this exact order:

```text
case_id,deletion_status,steps_json
```

Produce exactly one row per request. `deletion_status` is `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`. `steps_json` is an ordered JSON array containing findings, remediation actions, and verification checks. Use an empty array (`[]`) for `NOT_APPLICABLE`. Evidence references may be a `file_id`, `activity_id`, or `audit_id`. Determine the resource state at `audit_at` from the available evidence; reported workflow statuses and operation results are claims. Use `dataset/sample_output.csv` as the format reference.

The final file must contain 518 data rows sorted by `case_id` (plus the header row). The grader parses `steps_json` as JSON, so object-key order and whitespace do not matter; array order does. Order findings, remediation, and verification in that phase order. Within a phase, follow the operation order in the problem statement, then sort by `system_id` and `resource_id`.

---

## Evaluation

`output.csv` will be compared with hidden canonical answers. Scoring considers:

- deletion assessment accuracy;
- current and historical identity resolution;
- discovery of remaining data and recreation risks;
- correct policy application and evidence references; and
- completeness and ordering of remediation and verification steps.

Your `code.zip` must include:

```text
code/evaluation/evaluation_report.md
code/evaluation/usage_report.md
```

- `evaluation_report.md` must cover case, row, field, and sequence accuracy, at least three additional evaluation cases created by you, failures found, and improvements made.
- `usage_report.md` must cover the final full-dataset run, including model providers and names, model calls, input and output tokens, total and average tokens per request, and estimated total and per-request cost. Include per-model and overall totals when using multiple models.

**Important:** Place `evaluation_report.md` and `usage_report.md` inside `code/evaluation/` (matching `code/evaluation/main.py` in this starter layout), write your complete evaluation metrics, custom evaluation test cases, and token/cost breakdowns directly inside those Markdown files, and keep prompts in source code or Markdown files. Automated code evaluation ignores raw data files (`.csv`, `.tsv`, `.json`, `.jsonl`, `.sql`, `.log`), so content stored only in those formats will not be visible to the code judge or AI interviewer.

---

## Chat Transcript

This repository includes [`AGENTS.md`](./AGENTS.md), which instructs compatible AI coding tools to append conversation summaries to `log.txt` in the repository root:

| Platform | Path |
| --- | --- |
| macOS / Linux | `<repo root>/log.txt` |
| Windows | `<repo root>\log.txt` |

- Always launch your AI coding agent from the repository root (or explicitly ask it to read `./AGENTS.md` first) so every turn is logged to `log.txt` with the required `User Prompt`, `Agent Response Summary`, `Actions`, and `Context` sections.
- Upload `log.txt` directly as your `chat_transcript` submission on HackerRank.
- Do not include API keys, tokens, credentials, or secrets in prompts, code, configuration, or `log.txt`.

---

## Packaging `code.zip` and Submission

| Item | Description |
| --- | --- |
| `code.zip` | Runnable solution, prompts, configuration, `README.md`, and `evaluation/` reports |
| `output.csv` | One answer row for each of the 518 requests in `dataset/deletion_requests.csv` |
| `chat_transcript` | The root `log.txt` file generated by your coding agent |
| AI interview | Live explanation of your architecture, approach, and evaluation |

You may use any programming language, model, framework, or retrieval approach. Include clear setup and execution instructions in `README.md` inside `code.zip`.

To package `code.zip` from the repository root without bundling the dataset:

**macOS / Linux:**

```bash
zip -r code.zip README.md code -x "*/__pycache__/*" "*/.venv/*" "*/venv/*" "*/node_modules/*" "*/.git/*" "*/.DS_Store"
```

**Windows (PowerShell):**

```powershell
Compress-Archive -Path README.md, code -DestinationPath code.zip -Force
```

When packaging `code.zip`:

- Keep your evaluation reports in `code/evaluation/` so they are bundled automatically with `code` (or add `evaluation` to the archive command above if you placed them in a top-level `evaluation/` directory).
- Do **not** include `dataset/`, virtual environments (`.venv`, `venv`, `node_modules`), or build caches (`__pycache__`). On Windows, keep `.venv` at the repository root (outside `code/`) and remove any `code/__pycache__` folders before running `Compress-Archive`.
- Do **not** include nested archives (`.zip`, `.tar`, `.gz`, `.tgz`, `.7z`, `.rar`) inside `code.zip` — submissions containing nested archive files will be rejected.

Before submitting, confirm that:

- `output.csv` has the exact header `case_id,deletion_status,steps_json` and contains all 518 data rows sorted by `case_id`;
- every `steps_json` value is a valid JSON array with consecutive step numbers starting at `1`;
- findings cite valid evidence IDs, and `COMPLETE` verification steps cite evidence proving the current state;
- proposed remediation and future verification steps use an empty `evidence_id` (`""`);
- `code.zip` includes your runnable code, `README.md`, `code/evaluation/evaluation_report.md`, and `code/evaluation/usage_report.md`;
- `log.txt` follows the `AGENTS.md` turn format and is uploaded to the `chat_transcript` slot; and
- no API keys, credentials, real personal data, or sensitive configuration values are included.
