"""Investigator agent on the 32 samples: per-case review log and scores per proposal kind.

Run:  python3 code/evaluation/run_investigator.py --live   # calls Claude for uncached turns
      python3 code/evaluation/run_investigator.py          # cached answers only (offline)

The live pass runs with no proposal applied (the reviews are only recorded and
cached). Then each allow-set is replayed from the cache and scored, so every
proposal kind (add_account, drop, recategorize) is measured on its own and together.
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import score  # noqa: E402
from ghost import loaders  # noqa: E402

ALLOW_SETS = [("none (engine only)", set()), ("add_account", {"add_account"}), ("drop", {"drop"}),
              ("recategorize", {"recategorize"}), ("all", {"add_account", "drop", "recategorize"})]


def run(main_mod, allow, offline):
    pipe = main_mod.Pipeline(investigate=True, investigate_allow=allow, offline=offline)
    rows = pipe.run(loaders.load_sample_requests())
    return pipe, {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"])) for r in rows}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    main_mod = score.load_pipeline_module()
    gold = score.gold_cases()
    _, dev, held = score.split_ids(gold)
    pipe, _ = run(main_mod, set(), offline="--live" not in argv)
    print("per-case reviews (status, turns, tools, proposals):")
    for cid in sorted(pipe.reviews):
        rv = pipe.reviews[cid]
        props = [f"{p.decision}:{p.resource_id}{'->' + p.category if p.category else ''}" for p in rv.proposals]
        print(f"  {cid} {rv.status:12s} turns={rv.steps} tools={','.join(rv.tool_calls) or '-'} "
              f"conf={rv.confidence or '-'} proposals={props}")
    u = pipe.investigator.client.usage
    tok_in = sum(v for k, v in u.items() if k.endswith("|prompt_tokens"))
    tok_out = sum(v for k, v in u.items() if k.endswith("|completion_tokens"))
    print(f"model turns: live={u['live_calls']} cached={u['cached_calls']} failures={u['failures']} "
          f"| tokens in={tok_in} out={tok_out} | per case={(tok_in + tok_out) / max(len(pipe.reviews), 1):.0f}")
    print("statuses:", dict(Counter(rv.status for rv in pipe.reviews.values())))
    print(f"\n{'applied':22s} {'dev status/P/R/F1/exact':34s} {'held status/P/R/F1/exact':34s} accepted/rejected")
    for name, allow in ALLOW_SETS:
        p, pred = run(main_mod, allow, offline=True)
        out = []
        for ids in (dev, held):
            m = score.score(pred, gold, ids)
            P, R = m["tp"] / max(m["pred_steps"], 1), m["tp"] / max(m["gold_steps"], 1)
            out.append(f"{m['status_ok'] / m['cases']:.3f}/{P:.3f}/{R:.3f}/{2 * P * R / max(P + R, 1e-9):.3f}/"
                       f"{m['exact'] / m['cases']:.3f}")
        acc = sum(len(rv.accepted) for rv in p.reviews.values())
        rej = sum(len(rv.rejected) for rv in p.reviews.values())
        print(f"{name:22s} {out[0]:34s} {out[1]:34s} {acc}/{rej}")
        for cid, rv in sorted(p.reviews.items()):
            for a in rv.accepted:
                print(f"      accepted {cid} {a}")


if __name__ == "__main__":
    main()
