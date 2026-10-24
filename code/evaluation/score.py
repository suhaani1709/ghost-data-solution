"""Score predictions against sample_output.csv (the 32 public samples).

Run:  python3 code/evaluation/score.py            # runs the pipeline on the samples
      python3 code/evaluation/score.py PRED.csv   # scores an existing CSV

Metrics: status accuracy; exact case match; step-level P/R/F1 (steps as
multisets, step_no ignored); field-level accuracy (position-aligned, every
gold step counts); sequence accuracy (ordered (operation, system, resource)
list equal). Reported for all samples, the first 22 (dev) and last 10 (held out).
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghost import loaders  # noqa: E402

FIELDS = ("step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id")
DEV_SIZE = 22


def step_key(st):
    return tuple(st[f] for f in FIELDS if f != "step_no")


def score(pred, gold, case_ids):
    """pred/gold: {case_id: (status, steps)}."""
    m = Counter()
    for cid in case_ids:
        gs, gsteps = gold[cid]
        ps, psteps = pred.get(cid, ("", []))
        m["cases"] += 1
        m["status_ok"] += ps == gs
        m["exact"] += ps == gs and psteps == gsteps
        g, p = Counter(map(step_key, gsteps)), Counter(map(step_key, psteps))
        m["tp"] += sum((g & p).values())
        m["gold_steps"] += sum(g.values())
        m["pred_steps"] += sum(p.values())
        for i, gst in enumerate(gsteps):
            pst = psteps[i] if i < len(psteps) else {}
            for f in FIELDS:
                m[f"field_{f}"] += pst.get(f) == gst[f]
        seq = lambda steps: [(s["operation"], s["system_id"], s["resource_id"]) for s in steps]
        m["seq_ok"] += seq(psteps) == seq(gsteps)
    return m


def summary(m):
    n, gsteps = m["cases"], max(m["gold_steps"], 1)
    prec = m["tp"] / max(m["pred_steps"], 1)
    rec = m["tp"] / gsteps
    f1 = 2 * prec * rec / max(prec + rec, 1e-9)
    fields = " ".join(f"{f}={m[f'field_{f}'] / gsteps:.2f}" for f in FIELDS)
    return (f"cases={n} status_acc={m['status_ok'] / n:.3f} exact={m['exact'] / n:.3f} "
            f"step_P={prec:.3f} step_R={rec:.3f} step_F1={f1:.3f} seq_acc={m['seq_ok'] / n:.3f}\n"
            f"    field_acc: {fields}")


def load_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"]))
                for r in csv.DictReader(fh)}


def gold_cases():
    g = loaders.load_sample_output()
    return {r.case_id: (r.deletion_status, json.loads(r.steps_json)) for r in g.itertuples()}


def split_ids(gold):
    ids = sorted(gold)
    return ids, ids[:DEV_SIZE], ids[DEV_SIZE:]


def load_pipeline_module():
    """code/main.py by path (code/evaluation/main.py would shadow `import main`)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("ghost_main", Path(__file__).resolve().parents[1] / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def predict_samples():
    pipe = load_pipeline_module().Pipeline()
    rows = pipe.run(loaders.load_sample_requests())
    return pipe, {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"])) for r in rows}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    gold = gold_cases()
    pred = load_csv(argv[0]) if argv else predict_samples()[1]
    allc, dev, held = split_ids(gold)
    for name, ids in (("all", allc), ("dev(22)", dev), ("held-out(10)", held)):
        print(f"{name:13s} {summary(score(pred, gold, ids))}")


if __name__ == "__main__":
    main()
