"""Run the pipeline on the hand-built cases in code/evaluation/own_cases/.

Each case directory holds dataset/ (same schema as the real dataset/),
expected_output.csv (hand-derived before the pipeline was run) and CASE.md
(the derivation). A case passes when status and steps_json match exactly.
A failing case is reported as a finding; nothing here adjusts the pipeline.

Run:  python3 code/evaluation/run_own_cases.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import score  # noqa: E402
from ghost import loaders  # noqa: E402

OWN = Path(__file__).resolve().parent / "own_cases"


def run_case(case_dir):
    main_mod = score.load_pipeline_module()
    dataset = case_dir / "dataset"
    pipe = main_mod.Pipeline(dataset_dir=dataset)
    pred = {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"]))
            for r in pipe.run(loaders.load_deletion_requests(dataset))}
    gold = score.load_csv(case_dir / "expected_output.csv")
    return pred, gold


def short(steps):
    return [f'{s["operation"]} {s["system_id"]}/{s["resource_id"]} {s["evidence_id"] or "-"}'
            for s in steps]


def main():
    passed = 0
    cases = sorted(d for d in OWN.iterdir() if (d / "expected_output.csv").is_file())
    for d in cases:
        pred, gold = run_case(d)
        for cid in sorted(gold):
            ok = pred.get(cid) == gold[cid]
            passed += ok
            ps, psteps = pred.get(cid, ("<missing>", []))
            print(f"{'PASS' if ok else 'FAIL'}  {d.name:24s} expected {gold[cid][0]} {short(gold[cid][1])}")
            if not ok:
                print(f"      {'':24s} got      {ps} {short(psteps)}")
    print(f"{passed}/{len(cases)} own cases pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
