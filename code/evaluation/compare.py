"""Before/after table for pipeline options (measurement only).

Run:  python3 code/evaluation/compare.py base follow_refs ...

Each argument is a named config (CONFIGS). Per config: dev(22) and
held-out(10) status accuracy, step P/R/F1, exact match, linkage recall /
precision; dev resources recovered / extra vs the base config; planner
oracle (tests/test_planner_oracle.py); invalid rows in the 518-case output.
Held-out numbers are aggregates only.
"""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import score  # noqa: E402
import validate  # noqa: E402
from ghost import loaders  # noqa: E402

CONFIGS = {
    "base": {"follow_refs": False, "images": False,
             "replica_persist": "off", "activity_category": False, "find_account": False, "table_coverage": False, "use_llm": False, "link_after_audit": False, "explicit_absence": False},
    "follow_refs": {"follow_refs": True, "images": False,
             "replica_persist": "off", "activity_category": False, "find_account": False, "table_coverage": False, "use_llm": False, "link_after_audit": False, "explicit_absence": False},
    "images": {"follow_refs": False, "images": True,
             "replica_persist": "off", "activity_category": False, "find_account": False, "table_coverage": False, "use_llm": False, "link_after_audit": False, "explicit_absence": False},
    "follow+images": {"follow_refs": True, "images": True, "replica_persist": "off",
                      "activity_category": False, "find_account": False, "table_coverage": False, "use_llm": False, "link_after_audit": False, "explicit_absence": False},
    "replica_any": {"follow_refs": True, "images": True, "replica_persist": "any",
                    "activity_category": False, "find_account": False, "table_coverage": False, "use_llm": False, "link_after_audit": False, "explicit_absence": False},
    "replica_drift": {"follow_refs": True, "images": True, "replica_persist": "drift",
                      "activity_category": False, "find_account": False, "table_coverage": False, "use_llm": False, "link_after_audit": False, "explicit_absence": False},
    "drift+actcat": {"follow_refs": True, "images": True, "replica_persist": "drift",
                     "activity_category": True, "find_account": False, "table_coverage": False, "use_llm": False, "link_after_audit": False, "explicit_absence": False},
    "account": {"follow_refs": True, "images": True, "replica_persist": "drift",
                "activity_category": True, "find_account": True, "table_coverage": False, "use_llm": False, "link_after_audit": False, "explicit_absence": False},
    "table_cover": {"follow_refs": True, "images": True, "replica_persist": "drift",
                    "activity_category": True, "find_account": False, "table_coverage": True, "use_llm": False, "link_after_audit": False, "explicit_absence": False},
    "account+cover": {"follow_refs": True, "images": True, "replica_persist": "drift",
                      "activity_category": True, "find_account": True, "table_coverage": True,
                      "propagate_accounts": False},
    "propagate": {"follow_refs": True, "images": True, "replica_persist": "drift",
                  "activity_category": True, "find_account": True, "table_coverage": True,
                  "propagate_accounts": True, "use_llm": False, "link_after_audit": False, "explicit_absence": False},
    "after_audit": {"follow_refs": True, "images": True, "replica_persist": "drift",
                    "activity_category": True, "find_account": True, "table_coverage": True,
                    "propagate_accounts": True, "use_llm": False, "link_after_audit": True, "explicit_absence": False},
    "explicit_absence": {"follow_refs": True, "images": True, "replica_persist": "drift",
                         "activity_category": True, "find_account": True, "table_coverage": True,
                         "propagate_accounts": True, "use_llm": False, "explicit_absence": True, "link_after_audit": False},
    "after+explicit": {"follow_refs": True, "images": True, "replica_persist": "drift",
                       "activity_category": True, "find_account": True, "table_coverage": True,
                       "propagate_accounts": True, "use_llm": False, "link_after_audit": True,
                       "explicit_absence": True},
    "llm_wide_window": {"follow_refs": True, "images": True, "replica_persist": "drift",
                        "activity_category": True, "find_account": True, "table_coverage": True,
                        "propagate_accounts": True, "use_llm": True, "link_after_audit": True,
                        "explicit_absence": True, "finder_windows": ((75, 10),)},
    "llm": {"follow_refs": True, "images": True, "replica_persist": "drift",
            "activity_category": True, "find_account": True, "table_coverage": True,
            "propagate_accounts": True, "use_llm": True, "link_after_audit": True,
            "explicit_absence": True, "finder_windows": ((76, -39), (6, 6)), "status_match": True,
            "coverage_only_if_unobserved": False, "newest_account": True, "status_windows": 1,
            "scoped_bundles": True},  # default
}
# An option a config does not name is off, so older configs keep their meaning when
# Pipeline defaults change.
OPTIONS_OFF = {"follow_refs": False, "images": False, "replica_persist": "off",
               "activity_category": False, "find_account": False, "table_coverage": False,
               "propagate_accounts": False, "use_llm": False, "link_after_audit": False,
               "explicit_absence": False, "finder_windows": ((75, 10),), "status_match": False,
               "coverage_only_if_unobserved": False, "newest_account": False, "status_windows": None,
               "scoped_bundles": False}
for _cfg in CONFIGS.values():
    for _k, _v in OPTIONS_OFF.items():
        _cfg.setdefault(_k, _v)
    _cfg["offline"] = True      # evaluation never calls the model API: cached answers only


def resources(steps):
    return {(s["system_id"], s["resource_id"]) for s in steps}


def planner_oracle():
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parents[1] / "tests"),
                                                pattern="test_planner_oracle.py")
    res = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    return f"{res.testsRun - len(res.failures) - len(res.errors)}/{res.testsRun}"


def invalid_rows(pipe, main_mod):
    rows = pipe.run(loaders.load_deletion_requests())
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "output.csv"
        main_mod.write_output(rows, path)
        act = loaders.load_system_activity()
        _, _, _, bad, _ = validate.validate(path, loaders.load_deletion_requests(),
                                         loaders.load_evidence_files(),
                                         set(loaders.load_user_audit_log().audit_id),
                                         dict(zip(act.activity_id, act.event_time)))
    return len(bad)


def evaluate(name, base_linked=None):
    main_mod = score.load_pipeline_module()
    pipe = main_mod.Pipeline(**CONFIGS[name])
    rows = pipe.run(loaders.load_sample_requests())
    pred = {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"])) for r in rows}
    gold = score.gold_cases()
    _, dev, held = score.split_ids(gold)
    linked = {c: set(pipe.trace.get(c, {}).get("linked", {})) for c in gold}
    out = {}
    for split, ids in (("dev", dev), ("held", held)):
        m = score.score(pred, gold, ids)
        p = m["tp"] / max(m["pred_steps"], 1)
        r = m["tp"] / max(m["gold_steps"], 1)
        tp = sum(len(resources(gold[c][1]) & linked[c]) for c in ids)
        gn = sum(len(resources(gold[c][1])) for c in ids)
        pn = sum(len(linked[c]) for c in ids)
        out[split] = {"status": m["status_ok"] / m["cases"], "P": p, "R": r,
                      "F1": 2 * p * r / max(p + r, 1e-9), "exact": m["exact"] / m["cases"],
                      "linkR": tp / max(gn, 1), "linkP": tp / max(pn, 1)}
        if base_linked is not None:
            new = {c: linked[c] - base_linked[c] for c in ids}
            out[split]["recovered"] = sum(len(new[c] & resources(gold[c][1])) for c in ids)
            out[split]["extra"] = sum(len(new[c] - resources(gold[c][1])) for c in ids)
            out[split]["lost"] = sum(len((base_linked[c] - linked[c]) & resources(gold[c][1]))
                                     for c in ids)
    out["oracle"] = planner_oracle()
    out["invalid"] = invalid_rows(main_mod.Pipeline(**CONFIGS[name]), main_mod)
    return out, linked, pipe


def fmt(name, r):
    lines = []
    for split in ("dev", "held"):
        m = r[split]
        extra = (f" recov={m['recovered']} extra={m['extra']} lost={m['lost']}"
                 if "recovered" in m else "")
        lines.append(f"{name:14s} {split:4s} status={m['status']:.3f} P={m['P']:.3f} R={m['R']:.3f}"
                     f" F1={m['F1']:.3f} exact={m['exact']:.3f} linkR={m['linkR']:.3f}"
                     f" linkP={m['linkP']:.3f}{extra}")
    lines.append(f"{name:14s} oracle={r['oracle']} invalid_518={r['invalid']}")
    return "\n".join(lines)


def main(argv=None):
    names = (sys.argv[1:] if argv is None else argv) or ["base"]
    base, base_linked, _ = evaluate(names[0])
    print(fmt(names[0], base))
    for name in names[1:]:
        print(fmt(name, evaluate(name, base_linked)[0]))


if __name__ == "__main__":
    main()
