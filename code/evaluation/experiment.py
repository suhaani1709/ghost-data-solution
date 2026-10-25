"""One isolated experiment: Pipeline options -> gold metrics (dev / held-out) and a 518 row diff.

Run:  python3 code/evaluation/experiment.py '{"coverage_only_if_unobserved": true}' [BASELINE_CSV]

Offline (cached model answers only). The baseline is the delivered output.csv unless a path is given.
Prints status, step P/R/F1, exact, sequence and mean position-aligned field accuracy for dev and held-out,
then the 518 diff: rows changed, status flips, steps added / removed, evidence ids changed.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import score  # noqa: E402
from ghost import loaders  # noqa: E402

FIELDS = ("step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id")


def gold_metrics(pred: dict, gold: dict, ids: list[str]) -> str:
    m = score.score(pred, gold, ids)
    p, r = m["tp"] / max(m["pred_steps"], 1), m["tp"] / max(m["gold_steps"], 1)
    field = sum(m[f"field_{f}"] for f in FIELDS) / len(FIELDS) / max(m["gold_steps"], 1)
    return (f"status {m['status_ok'] / m['cases']:.3f} P {p:.3f} R {r:.3f} F1 {2 * p * r / max(p + r, 1e-9):.3f} "
            f"exact {m['exact'] / m['cases']:.3f} seq {m['seq_ok'] / m['cases']:.3f} field {field:.3f}")


def step_key(s: dict) -> tuple:
    return (s["system_id"], s["resource_id"], s["operation"])


def diff_518(base: dict, rows: list[dict]) -> str:
    changed = flips = added = removed = evid = 0
    for r in rows:
        b = base[r["case_id"]]
        if b == r:
            continue
        changed += 1
        flips += b["deletion_status"] != r["deletion_status"]
        bs = {step_key(s): s["evidence_id"] for s in json.loads(b["steps_json"])}
        rs = {step_key(s): s["evidence_id"] for s in json.loads(r["steps_json"])}
        added += len(rs.keys() - bs.keys())
        removed += len(bs.keys() - rs.keys())
        evid += sum(bs[k] != rs[k] for k in bs.keys() & rs.keys())
    return (f"518: rows changed {changed}, status flips {flips}, steps added {added}, removed {removed}, "
            f"evidence ids changed {evid}")


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    opts = json.loads(argv[0]) if argv else {}
    base_path = Path(argv[1]) if len(argv) > 1 else loaders.REPO_ROOT / "output.csv"
    main_mod = score.load_pipeline_module()
    gold = score.gold_cases()
    _, dev, held = score.split_ids(gold)
    pipe = main_mod.Pipeline(offline=True, **opts)
    pred = {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"]))
            for r in pipe.run(loaders.load_sample_requests())}
    print(f"options {opts}")
    print(f"  dev      {gold_metrics(pred, gold, dev)}")
    print(f"  held-out {gold_metrics(pred, gold, held)}")
    base = {r["case_id"]: r for r in csv.DictReader(open(base_path, newline="", encoding="utf-8"))}
    rows = main_mod.Pipeline(offline=True, **opts).run(loaders.load_deletion_requests())
    print(f"  {diff_518(base, rows)}")


if __name__ == "__main__":
    main()
