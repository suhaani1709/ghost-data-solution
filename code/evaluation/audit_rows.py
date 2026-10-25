"""Audit every output row against invariants derived from the 32 gold answers.

Run:  python3 code/evaluation/audit_rows.py [--out PATH]   (offline, cached model answers)

Each invariant is first checked on the gold sample answers (its gold pass rate is
printed); only invariants that hold on gold flag rows of the 518 output. Prints a
flag-count table and writes the flagged case_ids (no personal data) to --out.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import score  # noqa: E402
from ghost import intent, loaders, planner  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parents[3] / "orchestrate_research" / "AUDIT_518.md"
SAMPLE_CATEGORIES = {"USER_PROFILE", "SEARCH_INDEX_ENTRY", "USER_EXPORT", "SUPPORT_ATTACHMENT", "SUPPORT_MESSAGE",
                     "ANALYTICS_PROFILE", "MARKETING_PROFILE", "SECURITY_AUDIT_LOG", "ACCOUNT_TOMBSTONE",
                     "BACKUP_ARCHIVE", "DATA_FLOW"}


def resources(steps: list[dict]) -> set[tuple[str, str]]:
    return {(s["system_id"], s["resource_id"]) for s in steps}


def inv_one_account(status: str, steps: list[dict]) -> bool:
    return status == "NOT_APPLICABLE" or sum(s == "account_service" for s, _ in resources(steps)) == 1


def inv_structure(status: str, steps: list[dict]) -> bool:
    if [s["step_no"] for s in steps] != list(range(1, len(steps) + 1)):
        return False
    key = [(planner.PHASES.index(s["phase"]), planner.OP_ORDER[s["operation"]], s["system_id"], s["resource_id"])
           for s in steps]
    if key != sorted(key):
        return False
    if status == "COMPLETE":
        return all(s["phase"] == "VERIFICATION" for s in steps)
    if status == "INCOMPLETE":
        f = {(s["system_id"], s["resource_id"]) for s in steps if s["phase"] == "FINDING"}
        r = {(s["system_id"], s["resource_id"]) for s in steps if s["phase"] == "REMEDIATION"}
        v = {(s["system_id"], s["resource_id"]) for s in steps if s["phase"] == "VERIFICATION"}
        return bool(f) and f == r and r <= v
    return not steps


class Citations:
    """Is a cited file the latest file (captured <= audit_at) that mentions the resource?"""

    def __init__(self, obs: pd.DataFrame, manifest: pd.DataFrame):
        o = obs[obs.resource_id != ""]
        self.files = defaultdict(set)
        for s, r, f in zip(o.system_id, o.resource_id, o.file_id):
            self.files[(s, r)].add(f)
        self.cap = dict(zip(manifest.file_id, manifest.captured_at))

    def latest(self, step: dict, audit_at: str) -> bool | None:
        ev = step["evidence_id"]
        if ev not in self.cap:
            return None                     # activity/audit id or "" (not a file citation)
        mention = [f for f in self.files[(step["system_id"], step["resource_id"])] if self.cap[f] <= audit_at]
        if not mention:
            return None                     # absence proof by a covering snapshot
        return self.cap[ev] >= max(self.cap[f] for f in mention)


def provenance(pipe, case_id: str) -> dict[tuple[str, str], str]:
    """Strongest tier per linked resource: evidence > image > reference > finder > activity."""
    tr = pipe.trace.get(case_id, {})
    obs = pipe.obs
    kinds = dict(zip(obs.file_id, obs.file_kind))
    out = {}
    for key, sources in tr.get("linked", {}).items():
        tiers = set()
        for src in sources:
            if src.startswith("activity_"):
                tiers.add("finder" if key[0] == "account_service" else "activity")
            elif kinds.get(src) == "png":
                tiers.add("image")
            else:
                own = obs[(obs.file_id == src) & (obs.system_id == key[0]) & (obs.resource_id == key[1])]
                tiers.add("evidence" if (own.state != "REFERENCED").any() else "reference")
        for t in ("evidence", "image", "reference", "finder", "activity"):
            if t in tiers:
                out[key] = t
                break
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)
    main_mod = score.load_pipeline_module()
    gold = score.gold_cases()
    req = loaders.load_deletion_requests().set_index("case_id")
    sreq = loaders.load_sample_requests().set_index("case_id")
    out_rows = score.load_csv(loaders.REPO_ROOT / "output.csv")
    pipe = main_mod.Pipeline(offline=True)
    pipe.run(loaders.load_deletion_requests())
    cites = Citations(pipe.obs, loaders.load_evidence_files())
    flags: dict[str, list[str]] = defaultdict(list)
    print("invariant                               gold pass     518 flagged")

    def report(name, gold_ok, gold_n, flagged):
        holds = gold_ok == gold_n
        print(f"{name:38s} {gold_ok:3d}/{gold_n:<3d} {'holds' if holds else 'BROKEN':6s} "
              f"{len(flagged) if holds else '(not used)'}")
        if holds:
            for c in flagged:
                flags[c].append(name)

    # a. exactly one account per deletion case
    report("a one account_service resource", sum(inv_one_account(*gold[c]) for c in gold), len(gold),
           [c for c, v in out_rows.items() if not inv_one_account(*v)])
    # b. structure
    report("b structure / order / phases", sum(inv_structure(*gold[c]) for c in gold), len(gold),
           [c for c, v in out_rows.items() if not inv_structure(*v)])
    # c. citation is the latest mentioning file
    g = [cites.latest(s, sreq.audit_at[c]) for c in gold for s in gold[c][1] if s["evidence_id"]]
    g = [x for x in g if x is not None]
    o_bad = sorted({c for c, (st, steps) in out_rows.items() for s in steps
                    if s["evidence_id"] and cites.latest(s, req.audit_at[c]) is False})
    o_all = [cites.latest(s, req.audit_at[c]) for c, (st, steps) in out_rows.items() for s in steps if s["evidence_id"]]
    o_all = [x for x in o_all if x is not None]
    print(f"c citation = latest mentioning file     {sum(g):3d}/{len(g):<3d} (gold rate {sum(g) / len(g):.3f}); "
          f"518: {sum(o_all)}/{len(o_all)} = {sum(o_all) / max(len(o_all), 1):.3f}, rows with a non-latest citation "
          f"{len(o_bad)} (informational, gold itself is not 100%)")
    # d. per-system operation mix
    gmix = Counter((s["system_id"], s["operation"]) for c in gold for s in gold[c][1])
    omix = Counter((s["system_id"], s["operation"]) for _, steps in out_rows.values() for s in steps)
    gt, ot = sum(gmix.values()), sum(omix.values())
    print("d operation mix (share of steps)  gold  vs  518")
    for k in sorted(set(gmix) | set(omix), key=lambda k: -(gmix[k] / gt + omix[k] / ot)):
        print(f"    {k[0]:20s} {k[1]:26s} {100 * gmix[k] / gt:5.1f}%  {100 * omix[k] / ot:5.1f}%")
    # e. provenance tiers
    tiers = Counter()
    weak_rows = []
    for c in out_rows:
        prov = provenance(pipe, c)
        tiers.update(prov.values())
        if prov and all(t in ("finder", "activity", "reference") for t in prov.values()):
            weak_rows.append(c)
    print("e provenance tiers of linked resources:", dict(tiers), "| rows resting only on weak tiers:", len(weak_rows))
    for c in weak_rows:
        flags[c].append("e weak provenance only")
    # f. users with several requests
    idx = pipe.index
    by_user = defaultdict(list)
    for c in out_rows:
        by_user[idx.resolve_request(req.loc[c]).user_id].append(c)
    multi = {u: cs for u, cs in by_user.items() if len(cs) > 1}
    diff = [cs for cs in multi.values() if len({req.audit_at[c] for c in cs}) > 1]
    incons = [cs for cs in multi.values() if len({frozenset(resources(out_rows[c][1])) for c in cs}) > 1]
    print(f"f users with several requests: {len(multi)}; with different audit dates: {len(diff)}; "
          f"with different resource sets: {len(incons)}")
    for cs in incons:
        for c in cs:
            flags[c].append("f same user, different resources")
    # g. NOT_APPLICABLE
    na = [c for c, (st, _) in out_rows.items() if st == "NOT_APPLICABLE"]
    explicit = [c for c in na if intent.classify(req.request_text[c])[0] == intent.NON_DELETE]
    print(f"g NOT_APPLICABLE rows: {len(na)} (explicit non-deletion text: {len(explicit)})")
    # h. categories never exercised by the samples
    unseen = Counter()
    for c in out_rows:
        for s, r, cat, *_ in pipe.trace.get(c, {}).get("resources", []):
            if cat not in SAMPLE_CATEGORIES:
                unseen[cat] += 1
                flags[c].append(f"h unseen category {cat}")
    print("h categories the samples never exercise:", dict(unseen))
    table = Counter(f for fs in flags.values() for f in set(fs))
    print("\nflag counts:")
    for f, n in table.most_common():
        print(f"  {n:4d}  {f}")
    lines = ["# AUDIT_518 — flagged rows (case_ids only)", "",
             "Generated by `code/evaluation/audit_rows.py` (offline). Invariants are used only if they hold on gold.", ""]
    for f, n in table.most_common():
        cs = sorted((c for c, fs in flags.items() if f in fs), key=loaders.case_sort_key)
        lines += [f"## {f} ({n})", "", ", ".join(cs), ""]
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("written:", args.out)


if __name__ == "__main__":
    main()
