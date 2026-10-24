# Own case (g): refusal of deletion in Spanish (unseen wording)

**Input.** "Por favor, no eliminen mi cuenta. Todavía la uso para mis pedidos." ("Please do not
delete my account. I still use it for my orders.") A live profile row exists in evidence_g1.

**Hand derivation (written before running the pipeline).** §6.5: the text explicitly refuses
deletion, so nothing is authorized. The answer is NOT_APPLICABLE with `[]`. The text is in none
of the sentence tables, so this tests the cue fallback, which must fail closed.

**Expected:** `own_g,NOT_APPLICABLE,[]`
