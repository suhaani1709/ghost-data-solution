"""PDF evidence -> units, one per page (pdftotext -layout).

The category comes from what the document is, judged from its whole text
(a page alone may carry only a continuation header): an attachment's upload
properties, a retention register of disputed orders, or a signed audit
journal extract. A customer statement / anything else stays uncategorized.
State is PRESENT: the page itself shows the record exists.
"""
from . import parse_common as pc

def _document_category(text):
    low = text.lower()
    if "compliance journal" in low or "audit_record_" in low:
        return "SECURITY_AUDIT_LOG"
    if "disputed order" in low or "tax record" in low:
        return "LEGAL_HOLD_RECORD"
    if "attachment" in low:
        return "SUPPORT_ATTACHMENT"
    return ""


def parse_pdf(path):
    pages = pc.pdf_pages(path)
    cat = _document_category("\n".join(pages))
    out = []
    for page in pages:
        rids = sorted(set(pc.RESOURCE_ID.findall(page)))
        for rid in rids or [""]:
            out.append(pc.make_unit(system_id=pc.system_for(rid), resource_id=rid,
                                    category_hint=cat, state="PRESENT" if rid else "", text=page))
    return out
