"""Request intent: DELETE, NON_DELETE or UNKNOWN.

The request texts are built from a small, closed set of sentences. Clustering
the 518 evaluation texts by sentence gives 17 deletion openings (6 languages),
30 neutral follow-up sentences, and 10 one-off non-deletion texts. Each of
those was labelled by reading it.

A text gets a label only when *every* sentence in it is in the tables below and
the labels agree. Anything else is UNKNOWN, so a familiar opening followed by an
unseen sentence (which could reverse the intent) is never guessed. Keyword
regexes are deliberately not used: "correct treatment" or "remove" appear in
deletion texts too.
"""
from __future__ import annotations

import logging
import re
import unicodedata

log = logging.getLogger(__name__)

DELETE = "DELETE"
NON_DELETE = "NON_DELETE"
UNKNOWN = "UNKNOWN"

# Opening sentence -> (label, language)
OPENINGS = {
    # deletion templates, English
    "Please treat this message as a request for permanent account deletion.": (DELETE, "en"),
    "I would like to submit a request to delete this account and its personal data.": (DELETE, "en"),
    "I am requesting deletion of the account registered to this email address.": (DELETE, "en"),
    "Please erase the account linked to this email address.": (DELETE, "en"),
    "I am asking you to remove my account and the personal information linked to it.": (DELETE, "en"),
    "I no longer use this account and would like it permanently deleted.": (DELETE, "en"),
    "Please permanently delete the account associated with this email address.": (DELETE, "en"),
    "Please process a permanent account-deletion request for this email address.": (DELETE, "en"),
    "Please close my account and process the associated personal-data deletion.": (DELETE, "en"),
    "I would like the account associated with this address to be erased.": (DELETE, "en"),
    "Please begin the deletion process for the account using this email address.": (DELETE, "en"),
    "I want to close this account and have its associated personal data deleted.": (DELETE, "en"),
    # deletion templates, other languages
    "Solicito a exclusão permanente da conta associada a este e-mail.": (DELETE, "pt"),
    "Solicito la eliminación permanente de la cuenta asociada a este correo.": (DELETE, "es"),
    "Je demande la suppression définitive du compte associé à cette adresse e-mail.": (DELETE, "fr"),
    "このメールアドレスに関連するアカウントの完全な削除を依頼します。": (DELETE, "ja"),
    "이 이메일 주소에 연결된 계정의 영구 삭제를 요청합니다.": (DELETE, "ko"),
    # non-deletion one-offs (correction, opt-out, access, export, login help)
    "The mobile number on my profile is out of date.": (NON_DELETE, "en"),
    "Please stop the promotional emails.": (NON_DELETE, "en"),
    "I'd like to download my account information in a portable format.": (NON_DELETE, "en"),
    "I can't access my profile and need help resetting the login.": (NON_DELETE, "en"),
    "My surname is misspelled on the account.": (NON_DELETE, "en"),
    "Please remove me from marketing lists only.": (NON_DELETE, "en"),
    "Can you tell me what personal information you hold about me?": (NON_DELETE, "en"),
    "I need a copy of last year's invoices for my records.": (NON_DELETE, "en"),
    "Please change the email address used for this account.": (NON_DELETE, "en"),
    "Could you send me a copy of the information held on my account?": (NON_DELETE, "en"),
}

# Follow-up sentence -> label (None = neutral boilerplate, carries no intent)
FOLLOW_UPS = {
    # neutral follow-ups used by the deletion templates
    "Please contact me if you need information to verify the request.": None,
    "Please send a confirmation after the process finishes.": None,
    "Let me know when the request has been completed.": None,
    "A short confirmation when the process is complete is sufficient.": None,
    "Please let me know once the request has been reviewed.": None,
    "I would appreciate confirmation of the final outcome.": None,
    "Please confirm when the review is complete.": None,
    "Please confirm the result after completing the required checks.": None,
    "Please review any identifiers connected to this account as part of the request.": None,
    "Please review the account data that is eligible for deletion or de-identification.": None,
    "Please check the records connected to the account before confirming completion.": None,
    "Please follow the applicable retention and deletion requirements for the account.": None,
    "Please apply the request across the systems covered by your deletion policy.": None,
    "Please ensure the request is applied to the relevant account records.": None,
    "Please apply the correct treatment to records covered by the request.": None,
    "Please include information linked through current or earlier account identifiers.": None,
    "Please process this under the standard personal-data deletion procedure.": None,
    "Please complete the normal identity and data review for this request.": None,
    "Please handle any copies that fall within the scope of the deletion request.": None,
    "Please include records associated with the account under your privacy process.": None,
    "Verifiquem os identificadores atuais e anteriores conforme o processo de privacidade.": None,
    "Por favor, confirmem o resultado quando a análise terminar.": None,
    "개인정보 처리 절차에 따라 현재 및 이전 식별자를 검토해 주세요.": None,
    "검토가 완료되면 결과를 확인해 주세요.": None,
    "Revisen los identificadores actuales y anteriores según su política de privacidad.": None,
    "Por favor, confirmen el resultado cuando termine la revisión.": None,
    "プライバシー手続きに従い、現在および過去の識別情報を確認してください。": None,
    "確認が完了したら結果をお知らせください。": None,
    "Veuillez examiner les identifiants actuels et antérieurs conformément à votre procédure de confidentialité.": None,
    "Merci de confirmer le résultat une fois la vérification terminée.": None,
    # follow-ups of the non-deletion one-offs
    "Please replace it with the new one and leave the account active.": NON_DELETE,
    "I still need the account and my order history, so I am not asking for deletion.": NON_DELETE,
    "Please keep the account as it is.": NON_DELETE,
    "Do not close the account.": NON_DELETE,
    "Can you correct it without removing any of my records?": NON_DELETE,
    "I still want receipts and service messages for this account.": NON_DELETE,
    "This is an information request, not a request to erase it.": NON_DELETE,
    "Please leave my profile and purchase history in place.": NON_DELETE,
    "I want to continue using the service.": NON_DELETE,
    "I still use it, so please don't delete or change anything.": NON_DELETE,
}

# Sentences that explicitly refuse deletion (after normalize()). Used only for texts the
# strict tables cannot label: an UNKNOWN text containing one is NON_DELETE, not DELETE.
# Own case (a) phrasing and its variants, plus the explicit refusals among the
# non-deletion follow-ups above.
NEGATIONS = {
    "Please do not delete my account.", "Please don't delete my account.",
    "Do not delete my account.", "Don't delete my account.",
    "Please do not delete this account.", "Please don't delete this account.",
    "I do not want my account deleted.", "I don't want my account deleted.",
    "I do not want to delete my account.", "I don't want to delete my account.",
    "Please do not close my account.", "Please don't close my account.",
    "Do not close the account.",
    "I still need the account and my order history, so I am not asking for deletion.",
    "This is an information request, not a request to erase it.",
    "I still use it, so please don't delete or change anything.",
}

_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})
# Latin terminators need following whitespace; CJK terminators need none.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|(?<=[。！？])\s*")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).translate(_QUOTES)
    return " ".join(text.split())


def split_sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_SPLIT.split(normalize(text)) if s]


def classify(text: str) -> tuple[str, str]:
    """Return (label, reason). label is DELETE, NON_DELETE or UNKNOWN."""
    sentences = split_sentences(text)
    if not sentences:
        return UNKNOWN, "empty text"
    opening = OPENINGS.get(sentences[0])
    if opening is None:
        return UNKNOWN, f"unknown opening: {sentences[0]!r}"
    label = opening[0]
    for sentence in sentences[1:]:
        if sentence not in FOLLOW_UPS:
            return UNKNOWN, f"unknown follow-up: {sentence!r}"
        follow = FOLLOW_UPS[sentence]
        if follow is not None and follow != label:
            return UNKNOWN, f"follow-up {sentence!r} contradicts opening ({label})"
    return label, f"template ({opening[1]})"


def classify_requests(requests) -> tuple[dict[str, str], list[tuple[str, str]]]:
    """requests: DataFrame with case_id and request_text.

    Returns (labels, unknown): labels is {case_id: label}; unknown is a list
    of (case_id, reason) for every text that matched no known template.
    """
    labels, unknown = {}, []
    for row in requests.itertuples(index=False):
        label, reason = classify(row.request_text)
        labels[row.case_id] = label
        if label == UNKNOWN:
            unknown.append((row.case_id, reason))
    return labels, unknown


def effective_intent(text: str, warn: bool = True) -> str:
    """DELETE or NON_DELETE for the pipeline. The strict classify() is unchanged.

    UNKNOWN that contains an explicit refusal (NEGATIONS) is NON_DELETE. Other
    UNKNOWN falls back to DELETE (every deletion-request channel in the data is
    a deletion intake; all 32 samples are deletions). Both log a warning so the
    text can be reviewed and added to the tables.
    """
    label, reason = classify(text)
    if label == UNKNOWN:
        refusal = next((s for s in split_sentences(text) if s in NEGATIONS), None)
        if refusal is not None:
            if warn:
                log.warning("intent UNKNOWN but negates deletion (%r), NON_DELETE: %s", refusal, reason)
            return NON_DELETE
        if warn:
            log.warning("intent UNKNOWN, defaulting to DELETE: %s", reason)
        return DELETE
    return label
