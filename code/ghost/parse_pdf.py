"""PDF evidence -> units, one per page (pdftotext -layout).

The category comes from what the document is, judged from its whole text
(a page alone may carry only a continuation header): an attachment's upload
properties, a retention register of disputed orders, or a signed audit
journal extract. A customer statement / anything else stays uncategorized.
State is PRESENT: the page itself shows the record exists.

Run:  python3 code/ghost/parse_pdf.py --write-text   (regenerates code/pdf_text/*.md)
"""
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "ghost"

from . import loaders, parse_common as pc  # noqa: E402

def _document_category(text):
    low = text.lower()
    if "compliance journal" in low or "audit_record_" in low:
        return "SECURITY_AUDIT_LOG"
    if "disputed order" in low or "tax record" in low:
        return "LEGAL_HOLD_RECORD"
    if "attachment" in low:
        return "SUPPORT_ATTACHMENT"
    return ""


def parse_pdf(path, file_id=None):
    pages = pc.pdf_pages(path, file_id=file_id)
    cat = _document_category("\n".join(pages))
    out = []
    for page in pages:
        rids = sorted(set(pc.RESOURCE_ID.findall(page)))
        for rid in rids or [""]:
            out.append(pc.make_unit(system_id=pc.system_for(rid), resource_id=rid,
                                    category_hint=cat, state="PRESENT" if rid else "", text=page))
    return out


def write_text(dataset_dir=None):
    """Write PDF_TEXT_DIR/<file_id>.md for every PDF in the manifest (needs pdftotext)."""
    if pc.shutil.which("pdftotext") is None:
        raise SystemExit("pdftotext is required to regenerate the committed PDF text")
    dataset_dir = Path(dataset_dir or loaders.DATASET_DIR)
    pc.PDF_TEXT_DIR.mkdir(exist_ok=True)
    for f in loaders.load_evidence_files(dataset_dir).sort_values("file_id").itertuples():
        if f.file_path.lower().endswith(".pdf"):
            pages = pc.pdf_pages(dataset_dir / f.file_path, file_id=f.file_id)
            out = pc.PDF_TEXT_DIR / f"{f.file_id}.md"
            out.write_text(pc.pages_to_md(pages, f.file_path), encoding="utf-8")
            print(f"{out}: {len(pages)} pages")


if __name__ == "__main__" and sys.argv[1:] == ["--write-text"]:
    write_text()
