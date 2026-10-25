# Token usage and cost report

This report covers the final full-dataset run that produced `output.csv` (`python3 code/main.py`, 518
requests, 2026-10-25 17:59–18:07 IST, Claude Code available). Its output is byte-identical (SHA-256
7682a1ff…) to the `--offline`/`--no-llm` output and to the CSV in the submission. It uses three LLM agents, all on
**Claude Sonnet** (`claude-sonnet-5-5`), called through Claude Code's headless mode (`claude -p`,
`ghost/llm.py` `ClaudeCodeClient`):
- the intent agent reads every request text;
- the vision agent reads every PNG screenshot;
- the investigator agent reviews the engine-flagged uncertain cases with tools.

The intent and vision prompts changed in session 14 (explicit schemas, an UNSURE / `unreadable` flag), so
their 19 calls were made live. The investigator made 56 live calls and replayed 39 answers cached earlier that
day for identical requests (a cache key is SHA-256 of model, messages and parameters). Token counts come from
Claude Code's `usage` fields: input = new + cache-creation + cache-read prompt tokens; output = output tokens.
The `--offline` run of `code.zip` (no cache shipped, AGENTS.md §6.9) makes no model call.

## Final full-dataset run

| provider | model | agent | model calls | input tokens | output tokens | total tokens | API-equivalent cost |
|---|---|---|---|---|---|---|---|
| Anthropic (via Claude Code) | `claude-sonnet-5-5` | intent agent: 398 distinct texts, 8 batches (live) | 8 | 29,693 | 7,194 | 36,887 | $0.18 |
| Anthropic (via Claude Code) | `claude-sonnet-5-5` | vision agent: 11 screenshots (live) | 11 | 87,119 | 5,017 | 92,136 | $0.21 |
| Anthropic (via Claude Code) | `claude-sonnet-5-5` | investigator: 20 routed cases, live turns | 56 | 213,094 | 10,128 | 223,222 | $0.75 |
| Anthropic (via Claude Code) | `claude-sonnet-5-5` | investigator: replayed cached turns | 39 | 130,823 | 6,776 | 137,599 | $0.46 (estimate: live investigator cost per token × these tokens) |
| **overall** (one model, so per-model = overall) | | | **114** | **460,729** | **29,115** | **489,844** | **$1.60** (≈; $1.14 measured live + $0.46 estimated) |

| figure | value |
|---|---|
| average tokens per request | 489,844 / 518 = **945.6** |
| average tokens per investigated case | (223,222 + 137,599) / 20 = 18,041.1 |
| estimated total cost | **$1.60 API-equivalent**. The calls ran on a Claude Pro subscription, so no per-token charge was billed |
| estimated cost per request | $1.60 / 518 = **$0.0031** |

What the agents decided in this run:
- **Intent:** agreed with the sentence tables on 375/375 known texts and labelled the 23 unseen texts; 0 UNSURE,
  0 schema failures.
- **Vision:** 10/11 screenshots agree with the transcript. 1 disagreed (backup_restore_console), so the
  transcript was used; 0 schema failures, 0 flagged unreadable.
- **Investigator:** 20 reviews submitted; 0 proposals accepted, 2 rejected by `merge()`'s deterministic checks;
  0 output rows changed.

How the calls are kept low:
- **Batching and deduplication:** intent sends 50 texts per call, and identical texts are sent once.
- **Lean calls:** each call carries only the pipeline's own system prompt, with no Claude Code tools, MCP
  servers or project files (about 650 tokens of overhead, instead of the about 109,000 a default
  `claude -p` call loads).
- **Routing:** the investigator runs only on engine-flagged uncertain cases, capped by `--investigate-budget`.
- **Caching:** each answer is stored, keyed by SHA-256 of model, messages and parameters (by image content
  for screenshots), and is never requested twice.

Earlier final runs (sessions 9-13) replayed 90 cached answers (8 intent, 11 vision, 71 investigator turns) and
skipped uncached reviews. They gave the same output CSV, so the agents' effect on the output was nil in every run.

## Development usage (not part of the final run)

| what | model | calls | tokens | cost |
|---|---|---|---|---|
| investigator pilot on the 32 samples | `claude-sonnet-5-5` | 140 turns | 501,872 (481,192 in / 20,680 out) | $1.43 API-equivalent |
| all live Claude calls made (pilot + every final run; `usage_log.jsonl`) | `claude-sonnet-5-5` | 362 | 1,464,135 | $4.16 API-equivalent |
| first agent version, kept as `--backend openrouter` | `nvidia/nemotron-3.5-super-vl:free` (OpenRouter) | 31 | 105,817 | $0.00 (free model) |

Notes on the development figures:
- The live-call count includes the 75 live answers of the final run (the 39 replayed ones were logged when first made). It excludes failed attempts: the Pro session
  limit was hit once, there was one network error, and some free models were busy.
- A few one-off availability tests were run by hand and are not in the log (3 OpenRouter completions, 5 small
  `claude -p` checks).
- **Coding agent:** Claude Code (`claude-opus-5-5`) wrote and tested the code, and wrote
  `code/image_transcripts.md` by viewing the screenshots. Its own token use is not measured per task. The raw
  session traces are submitted separately as `agent-trace.zip`, which the participant assembles after the last
  session.

No API key, credential or configuration value is stored in the submission. Live calls need either a logged-in
Claude Code (default backend) or `OPENROUTER_API_KEY` from the environment or an uncommitted `.env` file
(`--backend openrouter`).
