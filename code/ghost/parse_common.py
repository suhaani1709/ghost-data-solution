"""Shared pieces for the evidence parsers: id and identifier regexes, the
category vocabulary, state inference and the unit -> observation shape.

Every parser returns "units": dicts with system_id, resource_id,
category_hint, state, identifiers, copy, event_time and raw_snippet.
observations.py adds file_id / captured_at / file_kind.

States (normalized): PRESENT, ABSENT, IDENTIFIABLE, ANONYMIZED, REDACTED,
ACTIVE, DISABLED, BLOCKED, REFERENCED (id only mentioned by another record),
or "" when the unit does not say.
"""
import logging
import re
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

# Committed `pdftotext -layout` output, one <file_id>.md per PDF (fallback when
# the binary is missing). Regenerate: python3 code/ghost/parse_pdf.py --write-text
PDF_TEXT_DIR = Path(__file__).resolve().parents[1] / "pdf_text"
PAGE_MARK = re.compile(r"^<!-- page \d+ -->\n", re.M)

RESOURCE_PREFIXES = ("audit_record", "data_flow", "email_delivery", "legal_hold", "tombstone",
                     "account", "analytics", "search", "support", "backup", "export",
                     "marketing", "object", "cache")
RESOURCE_ID = re.compile(r"(?<![\w.-])(?:%s)_\d+(?![\w.-])" % "|".join(RESOURCE_PREFIXES))

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
HASH = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{64}(?![0-9A-Fa-f])")
PHONE = re.compile(r"\+\d[\d ()-]{6,}\d")
USER_ID = re.compile(r"(?<![\w-])user_\d+(?![\w-])")

# Canonical owning system per resource-id prefix (1:1 in every sample answer).
SYSTEM_BY_PREFIX = {
    "account": "account_service", "analytics": "analytics_platform", "search": "search_service",
    "support": "support_platform", "audit_record": "security_service",
    "data_flow": "integration_service", "backup": "backup_service", "export": "export_service",
    "tombstone": "identity_service", "legal_hold": "legal_service",
    "marketing": "marketing_platform", "object": "object_storage", "cache": "cache_service",
    "email_delivery": "email_delivery_service",
}

CATEGORIES = {"USER_PROFILE", "SECONDARY_IDENTIFIER", "SEARCH_INDEX_ENTRY", "CACHE_ENTRY",
              "SUPPORT_MESSAGE", "SUPPORT_ATTACHMENT", "ANALYTICS_PROFILE", "PRODUCT_TELEMETRY",
              "USER_EXPORT", "MARKETING_PROFILE", "EMAIL_DELIVERY_LOG", "SECURITY_AUDIT_LOG",
              "LEGAL_HOLD_RECORD", "BACKUP_ARCHIVE", "ACCOUNT_TOMBSTONE", "DATA_FLOW"}

# Collection / table / service-export names -> category.
CATEGORY_BY_COLLECTION = {
    "customer_profiles": "USER_PROFILE", "profile_lookups": "USER_PROFILE",
    "customer_search_documents": "SEARCH_INDEX_ENTRY", "search_documents": "SEARCH_INDEX_ENTRY",
    "index_queries": "SEARCH_INDEX_ENTRY",
    "customer_analytics_reports": "ANALYTICS_PROFILE", "customer_analytics_profiles": "ANALYTICS_PROFILE",
    "profiles": "ANALYTICS_PROFILE",
    "support_conversations": "SUPPORT_MESSAGE", "support_records": "SUPPORT_MESSAGE",
    "tickets": "SUPPORT_MESSAGE", "ticket_attachments": "SUPPORT_ATTACHMENT",
    "customer_export_jobs": "USER_EXPORT", "customer_exports": "USER_EXPORT", "exports": "USER_EXPORT",
    "connector_configurations": "DATA_FLOW", "connector_subscriptions": "DATA_FLOW",
    "connectors": "DATA_FLOW",
    "backup_catalog": "BACKUP_ARCHIVE", "backup_restore_entries": "BACKUP_ARCHIVE",
    "restore_entries": "BACKUP_ARCHIVE",
    "security_audit_events": "SECURITY_AUDIT_LOG", "security_audit_records": "SECURITY_AUDIT_LOG",
    "audit_records": "SECURITY_AUDIT_LOG",
    "retained_order_records": "LEGAL_HOLD_RECORD",
    "deleted_customer_references": "ACCOUNT_TOMBSTONE",
}

EXPLICIT_STATES = {"FOUND": "PRESENT", "NOT_FOUND": "ABSENT", "IDENTIFIABLE": "IDENTIFIABLE",
                   "ANONYMIZED": "ANONYMIZED", "REDACTED": "REDACTED", "ACTIVE": "ACTIVE",
                   "DISABLED": "DISABLED", "BLOCKED": "BLOCKED"}

# Fields that hold a direct identifier when not null.
DIRECT_ID_FIELDS = ("email", "phone", "email_hash", "user_id", "customer_reference", "name",
                    "full_name", "display_name", "requester_email", "requester_name",
                    "requester_phone", "customer_email", "owner_email", "owner_phone",
                    "matched_value")
SUPPORT_ID_FIELDS = ("requester_email", "requester_name", "requester_phone", "matched_value")
SUPPORT_TEXT_FIELDS = SUPPORT_ID_FIELDS + ("message_text", "message_excerpt")


def prefix_of(resource_id):
    m = re.match(r"(.+)_\d+$", resource_id or "")
    return m.group(1) if m else ""


def system_for(resource_id, fallback=""):
    return SYSTEM_BY_PREFIX.get(prefix_of(resource_id), fallback)


def is_null(v):
    return v is None or (isinstance(v, str) and v.strip().lower() in ("", "null", "none"))


def truthy(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    return isinstance(v, str) and v.strip().lower() in ("true", "1", "yes", "allowed", "allow")


def falsy(v):
    if isinstance(v, bool):
        return not v
    if isinstance(v, (int, float)):
        return v == 0
    return isinstance(v, str) and v.strip().lower() in ("false", "0", "no", "deny", "denied")


def extract_identifiers(text):
    """Emails (lowercased), hashes (lowercased), phones (verbatim), user_ids."""
    return {
        "emails": sorted({e.lower() for e in EMAIL.findall(text)}),
        "hashes": sorted({h.lower() for h in HASH.findall(text)}),
        "phones": sorted({p.strip() for p in PHONE.findall(text)}),
        "user_ids": sorted(set(USER_ID.findall(text))),
    }


def has_direct_identifier(fields):
    for k in DIRECT_ID_FIELDS:
        if k in fields and not is_null(fields[k]):
            return True
    di = fields.get("direct_identifiers")
    if di is not None and not is_null(di) and str(di) not in ("0", "false"):
        return True
    return False


def infer_state(fields, category):
    """State from a unit's merged fields. Explicit results win; then absence
    markers; then category-specific flags; then plain presence."""
    result = str(fields.get("result", "")).strip()
    if result.upper() in EXPLICIT_STATES:
        return EXPLICIT_STATES[result.upper()]
    rows = str(fields.get("rows", "")).strip()
    status = str(fields.get("http_status", fields.get("status_code", ""))).strip()
    if rows == "0" or status == "404" or result.lower() == "miss" \
            or str(fields.get("total_hits", fields.get("total", ""))).strip() == "0":
        return "ABSENT"
    if "profile" in fields and fields["profile"] is None:
        return "ABSENT"
    if category == "DATA_FLOW" and "enabled" in fields:
        return "ACTIVE" if truthy(fields["enabled"]) else "DISABLED"
    if category == "BACKUP_ARCHIVE":
        if "decision" in fields:
            return "ACTIVE" if truthy(fields["decision"]) else "BLOCKED"
        if "restore_allowed" in fields:
            return "ACTIVE" if truthy(fields["restore_allowed"]) else "BLOCKED"
        if "eligible" in fields:
            blocked = truthy(fields.get("deletion_block", False))
            return "ACTIVE" if truthy(fields["eligible"]) and not blocked else "BLOCKED"
    if category == "USER_EXPORT":
        for k in ("download_available", "available"):
            if k in fields:
                return "PRESENT" if truthy(fields[k]) else "ABSENT"
    if category == "ANALYTICS_PROFILE":
        return "IDENTIFIABLE" if has_direct_identifier(fields) else "ANONYMIZED"
    if category == "ACCOUNT_TOMBSTONE":
        exposed = any(not is_null(fields.get(k)) for k in ("name", "email", "phone", "email_hash"))
        return "IDENTIFIABLE" if exposed else "REDACTED"
    if category == "SUPPORT_MESSAGE" and any(k in fields for k in SUPPORT_TEXT_FIELDS):
        text = " ".join(str(fields.get(k) or "") for k in ("message_text", "message_excerpt"))
        exposed = any(not is_null(fields.get(k)) for k in SUPPORT_ID_FIELDS)
        return "IDENTIFIABLE" if exposed or EMAIL.search(text) or PHONE.search(text) else "REDACTED"
    if rows not in ("", "0") or status == "200" or result.lower() == "hit" or fields.get("resource_id"):
        return "PRESENT"
    return ""


def snippet(text, limit=200):
    text = re.sub(r"\s+", " ", str(text)).strip()
    return text[:limit]


def make_unit(*, system_id, resource_id, category_hint, state, text, copy="unknown",
              event_time="", raw=None):
    return {
        "system_id": system_id or "",
        "resource_id": resource_id or "",
        "category_hint": category_hint or "",
        "state": state or "",
        "identifiers": extract_identifiers(text),
        "copy": copy,
        "event_time": event_time or "",
        "raw_snippet": snippet(raw if raw is not None else text),
    }


def reference_units(text, seen, system_hint="", copy="unknown", event_time=""):
    """Ids mentioned in a unit but not its own resource: emitted as REFERENCED."""
    out = []
    owners = " ".join(sorted(set(seen)))
    for rid in sorted(set(RESOURCE_ID.findall(text)) - set(seen)):
        unit = make_unit(system_id=system_for(rid, system_hint), resource_id=rid,
                         category_hint="", state="REFERENCED", text=text, copy=copy,
                         event_time=event_time)
        unit["referenced_by"] = owners      # the unit's own resource ids ("" if none)
        out.append(unit)
    return out


def pdf_pages(path, file_id=None):
    """pdftotext output split on form feeds, one string per page.

    Without the pdftotext binary, read the committed PDF_TEXT_DIR/<file_id>.md
    (same pages, byte for byte) and log a warning.
    """
    if shutil.which("pdftotext") is None:
        md = PDF_TEXT_DIR / f"{file_id}.md"
        if not file_id or not md.is_file():
            raise RuntimeError(f"pdftotext not found and no committed text {md} for {path}")
        log.warning("pdftotext not found; using committed text %s for %s",
                    md.relative_to(PDF_TEXT_DIR.parent), Path(path).name)
        return md_to_pages(md.read_text(encoding="utf-8"))
    out = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True,
                         check=True).stdout.decode("utf-8", "replace")
    pages = out.split("\f")
    if pages and not pages[-1].strip():
        pages = pages[:-1]
    return pages


def pages_to_md(pages, source):
    """Pages -> the committed Markdown form. Each page is a marker line, the
    page text and one added newline; md_to_pages() removes exactly that."""
    head = f"<!-- pdftotext -layout {source}; generated, do not edit -->\n"
    return head + "".join(f"<!-- page {i} -->\n{p}\n" for i, p in enumerate(pages, 1))


def md_to_pages(text):
    return [chunk[:-1] for chunk in PAGE_MARK.split(text)[1:]]
