"""Every text-readable evidence file -> one flat table of observations.

One row per (evidence unit, resource): file_id, captured_at (manifest),
file_kind, system_id, resource_id, category_hint, state, identifiers
(dict of sorted lists: emails, hashes, phones, user_ids), copy
(primary / replica / unknown), event_time, raw_snippet (<= 200 chars),
referenced_by (REFERENCED rows only: space-separated resource ids of the unit
that mentions the id; "" otherwise).

PNG screenshots are read from the hand transcript (parse_images.py) only
when images=True; otherwise skipped. No linking, no policy.

Run:  python3 code/ghost/observations.py   (prints the summary)
"""
import sys
from pathlib import Path

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "ghost"

from . import loaders, parse_images, parse_logs, parse_pdf, parse_records, parse_sql  # noqa: E402

COLUMNS = ["file_id", "captured_at", "file_kind", "system_id", "resource_id",
           "category_hint", "state", "identifiers", "copy", "event_time", "raw_snippet",
           "referenced_by"]
PARSERS = {
    "log": parse_logs.parse_log,
    "json": parse_records.parse_json,
    "txt": parse_records.parse_txt,
    "sql": parse_sql.parse_sql,
    "pdf": parse_pdf.parse_pdf,
}
SKIPPED_KINDS = {"png"}


def file_kind(path):
    return Path(path).suffix.lower().lstrip(".")


def build_observations(dataset_dir=None, images=False):
    dataset_dir = Path(dataset_dir or loaders.DATASET_DIR)
    parsers = dict(PARSERS, png=parse_images.parse_image) if images else PARSERS
    skipped = SKIPPED_KINDS - {"png"} if images else SKIPPED_KINDS
    manifest = loaders.load_evidence_files(dataset_dir).sort_values("file_id", kind="stable")
    rows = []
    for f in manifest.itertuples(index=False):
        kind = file_kind(f.file_path)
        if kind in skipped:
            continue
        parser = parsers.get(kind)
        if parser is None:
            raise ValueError(f"no parser for {f.file_path}")
        for unit in parser(dataset_dir / f.file_path):
            rows.append({"file_id": f.file_id, "captured_at": f.captured_at, "file_kind": kind,
                         "referenced_by": "", **unit})
    return pd.DataFrame(rows, columns=COLUMNS)


def to_records(df):
    """Plain, comparable form of the table (for determinism checks / export)."""
    return [tuple((c, repr(r[c])) for c in COLUMNS) for r in df.to_dict("records")]


def print_summary(df):
    print(f"observations: {len(df)}  files: {df.file_id.nunique()}")
    for col in ("file_kind", "system_id", "state"):
        print(f"\nper {col}:")
        for k, n in df[col].replace("", "<empty>").value_counts().sort_index().items():
            print(f"  {k:28s} {n:6d}")
    empty = df.category_hint == ""
    ref = df.state == "REFERENCED"
    print(f"\nempty category_hint: {empty.sum()} / {len(df)} = {empty.mean():.1%}"
          f"  (excluding REFERENCED mentions: {(empty & ~ref).sum()} / {(~ref).sum()}"
          f" = {(empty & ~ref).sum() / max((~ref).sum(), 1):.1%})")
    print("per category_hint:")
    for k, n in df.category_hint.replace("", "<empty>").value_counts().sort_index().items():
        print(f"  {k:28s} {n:6d}")


if __name__ == "__main__":
    print_summary(build_observations())
