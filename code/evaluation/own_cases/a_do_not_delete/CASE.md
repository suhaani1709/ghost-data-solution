# Own case (a): "please do not delete my account"

**Input.** One request from `ada.quill@example.com` (user_9001, current email):
"Please do not delete my account. I still use it every week." Evidence: one snapshot
bundle (evidence_a1, 2026-05-01) that still holds `account_9001` with the user's email.

**Hand derivation (written before running the pipeline).**
AGENTS.md §6.5: first decide whether `request_text` authorizes deletion. The text
explicitly refuses deletion, so nothing is authorized. problem_statement.md:
NOT_APPLICABLE rows use `[]`. The present profile row is irrelevant: no deletion
was requested, so it is not a violation.

**Expected:** `own_a,NOT_APPLICABLE,[]`
