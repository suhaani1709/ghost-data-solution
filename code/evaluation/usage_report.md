# Token usage and cost report

This report covers the final full-dataset run that produced `output.csv` (`python3 code/main.py`,
518 requests).

**The run makes zero model API calls.** Every step is deterministic Python (stdlib + pandas):
request intent (sentence tables plus a regex cue fallback for unseen wording, in `code/ghost/intent.py`), identity resolution, evidence parsing,
linking, state reconstruction, policy mapping and step planning. The code imports no model SDK,
opens no network connection and reads no API key or environment secret.

## Final full-dataset run

| model provider | model name | model calls | input tokens | output tokens | total tokens | avg tokens / request | est. total cost | est. cost / request |
|---|---|---|---|---|---|---|---|---|
| none | none (no model is called) | 0 | 0 | 0 | 0 | 0 (0 / 518) | $0.00 | $0.00 |
| **overall** | | **0** | **0** | **0** | **0** | **0** | **$0.00** | **$0.00** |

Only one "model" row exists because no model is used, so the per-model and overall totals coincide.
The run takes about 2 seconds on a laptop CPU (1.6 s measured, peak RSS 140 MB).

## Model use during development (not part of the run above)

- **Coding agent:** Claude Code with model `claude-opus-5-5` (Anthropic) wrote and tested the code.
  Every session turn is logged in `log.txt` (the chat transcript).
- **Screenshot transcription:** the 11 PNG screenshots under `dataset/evidence/images/` were viewed and
  transcribed by Claude Code during development, without OCR. The result was committed as
  `code/image_transcripts.md`, which `code/ghost/parse_images.py` validates against the identity
  data and parses at run time. At run time this is a file read, not a model call.
- **PDFs:** read with `pdftotext` (poppler). Their text is also committed as `code/pdf_text/*.md`
  as a fallback. No model is involved.
- **Intent and all other logic:** deterministic code. The intent tables were written by reading the
  request texts during development.

**Development token counts and cost: not reported.** We did not measure the tokens or cost of the
development sessions, including the screenshot transcription, per task. Any number here would be a
guess. The raw session traces, which hold per-message usage, are submitted separately in `agent-trace.zip`.
The challenge asks for the usage of the final run, and that is exactly zero.
