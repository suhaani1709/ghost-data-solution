"""Contract check for an output CSV (problem_statement.md / AGENTS.md §6.3-6.6).

Run:  python3 code/evaluation/validate.py output.csv [--sample]
Exit code 0 when every check passes. Prints one line per failed check type,
then one line per warning type (warnings do not make a row invalid).
COMPLETE with steps [] is a warning: problem_statement.md allows it (the
zero-link rule, NOTES.md); INCOMPLETE with [] is an error.
"""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghost import loaders, planner  # noqa: E402

STEP_KEYS = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}
STATUSES = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}


def validate(path, requests, manifest, audit_ids, activity_times):
    errors = Counter()
    examples = {}
    bad = set()     # case_ids of rows with at least one failed check
    warnings = Counter()

    def err(kind, case_id):
        errors[kind] += 1
        examples.setdefault(kind, case_id)
        bad.add(case_id)

    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != loaders.OUTPUT_COLUMNS:
            err("bad header", str(reader.fieldnames))
        rows = list(reader)
    ids = [r["case_id"] for r in rows]
    if ids != loaders.sort_case_ids(ids):
        err("rows not in numeric case_id order", "")
    if Counter(ids) != Counter(requests.case_id):
        err("case_id set differs from requests", f"{len(ids)} rows")
    audit = dict(zip(requests.case_id, requests.audit_at))
    captured = dict(zip(manifest.file_id, manifest.captured_at))
    for r in rows:
        cid = r["case_id"]
        if r["deletion_status"] not in STATUSES:
            err("bad deletion_status", cid)
        try:
            steps = json.loads(r["steps_json"])
        except ValueError:
            err("invalid JSON", cid)
            continue
        if not isinstance(steps, list):
            err("steps_json not an array", cid)
            continue
        status = r["deletion_status"]
        if status == "NOT_APPLICABLE" and steps:
            err("NOT_APPLICABLE with steps", cid)
        if status == "INCOMPLETE" and not steps:
            err("INCOMPLETE with no steps", cid)
        if status == "COMPLETE" and not steps:
            warnings["COMPLETE with no steps"] += 1
            examples.setdefault("COMPLETE with no steps", cid)
        phase_idx = -1
        for i, st in enumerate(steps, 1):
            if not isinstance(st, dict) or set(st) != STEP_KEYS:
                err("step keys", cid)
                continue
            if st["step_no"] != i:
                err("step_no not consecutive from 1", cid)
            op = st["operation"]
            if op not in planner.PHASE_OF:
                err("unknown operation", cid)
                continue
            if st["phase"] != planner.PHASE_OF[op] or st["state"] != planner.STATE_OF[op]:
                err("operation/phase/state mismatch", cid)
            p = planner.PHASES.index(planner.PHASE_OF[op])
            if p < phase_idx:
                err("phase order", cid)
            phase_idx = max(phase_idx, p)
            ev = st["evidence_id"]
            if status == "COMPLETE" and st["phase"] != "VERIFICATION":
                err("COMPLETE with non-verification step", cid)
            if status == "COMPLETE" or st["phase"] == "FINDING":
                if not ev:
                    err("missing evidence_id", cid)
                elif ev in captured:
                    if captured[ev] > audit[cid]:
                        err("evidence captured after audit_at", cid)
                elif ev in activity_times:
                    if activity_times[ev] > audit[cid]:
                        err("activity after audit_at", cid)
                elif ev not in audit_ids:
                    err("unknown evidence_id", cid)
            elif ev:
                err("future step with evidence_id", cid)
    return len(rows), errors, examples, bad, warnings


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--sample", action="store_true", help="validate against the sample requests")
    args = ap.parse_args(argv)
    requests = loaders.load_sample_requests() if args.sample else loaders.load_deletion_requests()
    activity = loaders.load_system_activity()
    n, errors, examples, bad, warnings = validate(args.path, requests, loaders.load_evidence_files(),
                                   set(loaders.load_user_audit_log().audit_id),
                                   dict(zip(activity.activity_id, activity.event_time)))
    if not errors:
        print(f"VALID: {n} rows, all checks passed (invalid rows: 0)")
    else:
        print(f"INVALID: {len(bad)} of {n} rows")
        for kind, count in errors.most_common():
            print(f"  {count:4d}  {kind}  (e.g. {examples[kind]})")
    for kind, count in warnings.most_common():
        print(f"  WARNING {count:4d}  {kind}  (e.g. {examples[kind]})")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
