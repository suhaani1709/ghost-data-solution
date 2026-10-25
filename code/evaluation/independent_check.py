"""Independent re-derivation of linked resources from RAW evidence text (no observations table).

Run:  python3 code/evaluation/independent_check.py [N]   (default 40 stratified rows)

For each sampled row: tokens = user_id, every current/historical email, SHA-256 of
each email, phones (from the CSVs directly). A resource is independently linked
when a raw "record" mentions both a token and the resource id: a JSON object with
a resource_id, a SQL INSERT line, a log trace (lines sharing a trace id), a text
line, a PDF page or an image-transcript row. The script diffs those sets against
output.csv and prints every disagreement for manual decision. Counts and ids only.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "dataset"
RID = re.compile(r"(?<![\w.-])(?:audit_record|data_flow|email_delivery|legal_hold|tombstone|account|analytics|search|"
                 r"support|backup|export|marketing|object|cache)_\d+(?![\w.-])")
TRACE = re.compile(r"\b(?:tr-\d+|requestId=\S+|trace_id[\"=: ]+[\w-]+)")


def sha(e: str) -> str:
    return hashlib.sha256(e.strip().lower().encode()).hexdigest()


def records(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".json":
        out = []

        def walk(o):
            if isinstance(o, dict):
                if "resource_id" in o:
                    out.append(json.dumps(o))
                    return
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(json.loads(text))
        return out
    if path.suffix == ".log":
        groups = defaultdict(list)
        for i, line in enumerate(text.splitlines()):
            m = TRACE.search(line)
            groups[m.group(0) if m else f"line{i}"].append(line)
        return ["\n".join(v) for v in groups.values()]
    return text.splitlines()


def load():
    files = {}
    for r in csv.DictReader(open(DS / "evidence_files.csv")):
        p = DS / r["file_path"]
        if p.suffix in (".json", ".log", ".sql", ".txt"):
            files[r["file_id"]] = (r["captured_at"], records(p))
        elif p.suffix == ".pdf":
            md = ROOT / "code" / "pdf_text" / f"{r['file_id']}.md"
            files[r["file_id"]] = (r["captured_at"], md.read_text().split("<!-- page"))
        elif p.suffix == ".png":
            t = (ROOT / "code" / "image_transcripts.md").read_text()
            sec = t.split(f"## {r['file_id']} ")[1].split("\n## ")[0] if f"## {r['file_id']} " in t else ""
            files[r["file_id"]] = (r["captured_at"], [ln for ln in sec.splitlines() if "| OWN |" in ln])
    return files


def identities():
    ids = {r["user_id"]: {r["user_id"], r["email"].lower(), sha(r["email"]), r["phone"], r["email_hash"].lower()}
           for r in csv.DictReader(open(DS / "user_identities.csv"))}
    email_user = {r["email"].lower(): r["user_id"] for r in csv.DictReader(open(DS / "user_identities.csv"))}
    for r in csv.DictReader(open(DS / "user_audit_log.csv")):
        for v in (r["old_value"], r["new_value"]):
            if v:
                ids[r["user_id"]] |= {v.lower(), sha(v)} if r["field_name"] == "email" else {v}
                if r["field_name"] == "email":
                    email_user[v.lower()] = r["user_id"]
    return ids, email_user


def main(argv=None):
    n = int((argv or sys.argv[1:] or ["40"])[0])
    files = load()
    ids, email_user = identities()
    out = {r["case_id"]: r for r in csv.DictReader(open(ROOT / "output.csv"))}
    req = {r["case_id"]: r for r in csv.DictReader(open(DS / "deletion_requests.csv"))}
    rows = [c for c in out if out[c]["deletion_status"] != "NOT_APPLICABLE"]
    pick = rows[:: max(1, len(rows) // n)][:n]      # stratified by position in the numeric order
    agree = only_out = only_ind = 0
    for c in pick:
        uid = email_user.get(req[c]["email"].strip().lower())
        toks = {t for t in ids[uid] if t}
        pat = re.compile(r"(?<![\w.@+-])(?:%s)(?![\w@-]|\.\w)" % "|".join(re.escape(t.lower()) for t in toks))
        ind = set()
        for fid, (cap, recs) in files.items():
            for rec in recs:
                if pat.search(rec.lower()):
                    ind |= set(RID.findall(rec))
        mine = {s["resource_id"] for s in json.loads(out[c]["steps_json"])}
        a, o, i = mine & ind, mine - ind, ind - mine
        agree += len(a); only_out += len(o); only_ind += len(i)
        if o or i:
            print(f"{c}: output-only {sorted(o)} | independent-only {sorted(i)}")
    print(f"{len(pick)} rows: agree {agree}, output-only {only_out}, independent-only {only_ind}")


if __name__ == "__main__":
    main()
