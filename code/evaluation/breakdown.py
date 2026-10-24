"""Failure breakdown of the pipeline on the 32 samples (diagnosis only).

Run:  python3 code/evaluation/breakdown.py

- status accuracy + confusion matrix (all 32)
- linkage recall / precision: gold resources = (system_id, resource_id) in
  the gold steps; predicted = resources the linker linked
- dev (first 22 by case_id): per-case MISSED / EXTRA counts, 5 worst cases,
  and the most common failure types with owning layer and one example
- held-out (last 10): aggregate numbers only
"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import score  # noqa: E402
from ghost import loaders  # noqa: E402

LAYERS = {
    "gold resource not linked (absent from parsed text evidence)": "linking",
    "gold resource not linked (in evidence, no identifier match)": "linking",
    "extra resource linked": "linking",
    "wrong treatment for resource": "category",
    "missed finding (predicted compliant)": "state",
    "false finding (gold compliant)": "state",
    "wrong evidence_id": "citation",
    "same steps, wrong order": "ordering",
}


def resources(steps):
    return {(s["system_id"], s["resource_id"]) for s in steps}


def by_resource(steps):
    out = defaultdict(list)
    for s in steps:
        out[(s["system_id"], s["resource_id"])].append(s)
    return out


def verification_op(steps):
    return next((s["operation"] for s in steps if s["phase"] == "VERIFICATION"), None)


def classify_failures(cid, gold, pred, linked, audit_at, obs):
    gs, gsteps = gold
    ps, psteps = pred
    found = []
    g_res, p_by, g_by = resources(gsteps), by_resource(psteps), by_resource(gsteps)
    for key in sorted(g_res - set(linked)):
        rows = obs[(obs.system_id == key[0]) & (obs.resource_id == key[1]) & (obs.captured_at <= audit_at)]
        found.append("gold resource not linked (in evidence, no identifier match)" if len(rows)
                     else "gold resource not linked (absent from parsed text evidence)")
    for key in sorted(set(linked) - g_res):
        found.append("extra resource linked")
    for key in sorted(g_res & set(p_by)):
        g, p = g_by[key], p_by[key]
        if verification_op(g) != verification_op(p):
            found.append("wrong treatment for resource")
            continue
        g_find = any(s["phase"] == "FINDING" for s in g)
        p_find = any(s["phase"] == "FINDING" for s in p)
        if g_find and not p_find and gs == "INCOMPLETE":
            found.append("missed finding (predicted compliant)")
        elif p_find and not g_find:
            found.append("false finding (gold compliant)")
        elif ps == gs:
            g_ev = {s["operation"]: s["evidence_id"] for s in g if s["evidence_id"]}
            p_ev = {s["operation"]: s["evidence_id"] for s in p if s["evidence_id"]}
            if g_ev != p_ev:
                found.append("wrong evidence_id")
    if Counter(map(score.step_key, gsteps)) == Counter(map(score.step_key, psteps)) \
            and [score.step_key(s) for s in gsteps] != [score.step_key(s) for s in psteps]:
        found.append("same steps, wrong order")
    return found


def main():
    gold = score.gold_cases()
    pipe, pred = score.predict_samples()
    requests = loaders.load_sample_requests().set_index("case_id")
    allc, dev, held = score.split_ids(gold)

    statuses = ["COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"]
    conf = Counter((gold[c][0], pred[c][0]) for c in allc)
    ok = sum(n for (g, p), n in conf.items() if g == p)
    print(f"STATUS accuracy {ok}/{len(allc)} = {ok / len(allc):.3f}   confusion (rows gold, cols pred):")
    print("  " + " " * 14 + "".join(f"{s[:10]:>12s}" for s in statuses))
    for g in statuses:
        print(f"  {g:14s}" + "".join(f"{conf[(g, p)]:12d}" for p in statuses))

    def used(c):
        """Resources the pipeline used: evidence links plus late links (added to INCOMPLETE only)."""
        t = pipe.trace.get(c, {})
        late = {r[:2] for r in t.get("late", ())} if pred[c][0] == "INCOMPLETE" else set()
        return set(t.get("linked", {})) | late

    def linkage(ids):
        tp = gold_n = pred_n = 0
        per = {}
        for c in ids:
            g, p = resources(gold[c][1]), used(c)
            tp += len(g & p)
            gold_n += len(g)
            pred_n += len(p)
            per[c] = (len(g - p), len(p - g), len(g))
        return tp, gold_n, pred_n, per

    for name, ids in (("dev(22)", dev), ("held-out(10)", held), ("all(32)", allc)):
        tp, gn, pn, _ = linkage(ids)
        print(f"LINKAGE {name:12s} recall {tp}/{gn} = {tp / max(gn, 1):.3f}   "
              f"precision {tp}/{pn} = {tp / max(pn, 1):.3f}")

    _, _, _, per = linkage(dev)
    print("DEV per-case MISSED/EXTRA (of gold):",
          " ".join(f"{c}:{m}/{e}({g})" for c, (m, e, g) in per.items()))
    worst = sorted(per.items(), key=lambda kv: (-(kv[1][0] + kv[1][1]), kv[0]))[:5]
    print("DEV 5 worst:", ", ".join(f"{c} (missed {m}, extra {e})" for c, (m, e, _) in worst))

    failures, example = Counter(), {}
    for c in dev:
        for f in classify_failures(c, gold[c], pred[c], used(c),
                                   requests.audit_at[c], pipe.obs):
            failures[f] += 1
            example.setdefault(f, c)
    print("DEV top failure types (occurrences, example, layer):")
    for f, n in failures.most_common(5):
        print(f"  {n:3d}  {f:62s} e.g. {example[f]:8s} layer={LAYERS[f]}")
    rest = [(f, n) for f, n in failures.most_common()[5:]]
    if rest:
        print("  others:", ", ".join(f"{f}={n}" for f, n in rest))
    print(f"CATEGORY fallbacks (samples run): {pipe.resolver.fallbacks}"
          f" {dict(pipe.resolver.fallback_log)} | state coercions: {dict(pipe.coercions)}"
          f" | pipeline stats: {dict(pipe.stats)}")


if __name__ == "__main__":
    main()
