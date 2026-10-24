"""PNG evidence via the hand transcript in code/image_transcripts.md (no OCR).

Each `## evidence_NN — <file name>` section holds one table, one row per
evidence unit: row | system_id | resource_id | role | user_id | email | phone
| state | category. role OWN = the unit's own resource; REF:<owner> = an id
the unit only mentions (a REFERENCED unit, referenced_by=<owner>).
Identifiers are taken verbatim from the table ("—" = none), emails lowercased.

validate() checks the transcript against the known universe: every email,
phone and user_id must exist in the identities data, every resource id must
match the resource-id prefix pattern. Failures are reported as suspected
misreads; nothing is corrected.

Run:  python3 code/ghost/parse_images.py   (prints units and validation)
"""
import re
import sys
from functools import lru_cache
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "ghost"

from . import parse_common as pc  # noqa: E402

TRANSCRIPT = Path(__file__).resolve().parents[1] / "image_transcripts.md"
HEADING = re.compile(r"^## (evidence_\d+) — (\S+\.png)\s*$")
TABLE_COLUMNS = ["row", "system_id", "resource_id", "role", "user_id", "email", "phone",
                 "state", "category"]
NONE = {"", "—", "-"}


def _cell(v):
    v = v.strip()
    return "" if v in NONE else v


def parse_transcript(text):
    """{file name: [row dict]} from the transcript markdown."""
    out, current, header = {}, None, None
    for line in text.splitlines():
        m = HEADING.match(line)
        if m:
            current, header = m.group(2), None
            out[current] = []
            continue
        if line.startswith("## "):
            current = None
            continue
        if current is None or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = cells
            if header != TABLE_COLUMNS:
                raise ValueError(f"unexpected image table header in {current}: {header}")
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        out[current].append(dict(zip(header, map(_cell, cells))))
    return out


@lru_cache(maxsize=1)
def _transcript(path=TRANSCRIPT):
    return parse_transcript(Path(path).read_text(encoding="utf-8"))


def row_to_unit(row):
    rid = row["resource_id"]
    role = row["role"]
    referenced = role.startswith("REF:")
    text = " ".join(row[c] for c in ("resource_id", "user_id", "email", "phone") if row[c])
    unit = pc.make_unit(system_id=row["system_id"] or pc.system_for(rid), resource_id=rid,
                        category_hint="" if referenced else row["category"],
                        state="REFERENCED" if referenced else row["state"], text=text,
                        raw=f"{row['row']}: {text}")
    unit["identifiers"] = {
        "emails": [row["email"].lower()] if row["email"] else [],
        "hashes": [],
        "phones": [row["phone"]] if row["phone"] else [],
        "user_ids": [row["user_id"]] if row["user_id"] else [],
    }
    if referenced:
        unit["referenced_by"] = role[len("REF:"):].strip()
    return unit


def parse_image(path):
    """Units for one PNG, from the transcript (none if it is not transcribed)."""
    return [row_to_unit(r) for r in _transcript().get(Path(path).name, []) if r["resource_id"]]


def validate(transcript, emails, phones, user_ids):
    """[(file name, value, problem)] for every value outside the known universe."""
    bad = []
    for name, rows in sorted(transcript.items()):
        for r in rows:
            if r["resource_id"] and not pc.RESOURCE_ID.fullmatch(r["resource_id"]):
                bad.append((name, r["resource_id"], "resource id does not match a prefix pattern"))
            if r["user_id"] and r["user_id"] not in user_ids:
                bad.append((name, r["user_id"], "user_id not in identities"))
            if r["email"] and r["email"].lower() not in emails:
                bad.append((name, r["email"], "email not in identities"))
            if r["phone"] and r["phone"] not in phones:
                bad.append((name, r["phone"], "phone not in identities"))
    return bad


def main():
    from . import identity
    idx = identity.IdentityIndex.from_dataset()
    emails = {e for s in idx.sets.values() for e in s.emails}
    phones = {p for s in idx.sets.values() for p in s.phones}
    transcript = _transcript()
    n = sum(len(v) for v in transcript.values())
    print(f"transcribed images: {len(transcript)}  rows: {n}")
    for name, value, problem in validate(transcript, emails, phones, set(idx.sets)):
        print(f"suspected misread: {name}: {value} ({problem})")


if __name__ == "__main__":
    main()
