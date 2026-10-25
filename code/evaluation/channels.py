"""Diagnostic: which activity channel could link gold resources that never
appear in parsed text evidence (diagnosis only, the pipeline is untouched).

Run:  python3 code/evaluation/channels.py

Each channel, alone, proposes (system_id, resource_id) pairs for a case on
top of the pipeline's evidence-linked set L:
  A  any activity row with requested_at <= event_time <= audit_at
  B  LINK_RESOURCE_IDENTITY rows (<= audit_at) naming one of the user's tokens
  C  A restricted to source_system == deletion_worker
  D  resource-number convention: resource suffix (<= 3 digits) == user number
  N  name channel: an evidence unit of the resource (<= audit_at, not a mere
     REFERENCED mention) whose raw_snippet contains the user's full name
     (exact substring; snippets are cut at 200 chars, so this undercounts)
Reported on dev(22): activity-only gold recovered, extra (wrong) resources
added, resulting linkage recall / precision, extras that are other dev
cases' gold resources. Held-out(10): aggregates only.

Run:  python3 code/evaluation/channels.py --accounts
Account finder diagnostics: the kept finder vs constraint propagation
(account_finder.propagate) per round, and a forced pick (closest delete to
reported_at, user number as tie-break) for what stays ambiguous, by margin
between the first and second candidate. Counts only; held-out aggregates.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import score  # noqa: E402
from ghost import linking, loaders  # noqa: E402

TOKEN = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]+|\buser_\d+\b")


def resources(steps):
    return {(s["system_id"], s["resource_id"]) for s in steps}


class Channels:
    def __init__(self, obs, activity):
        self.act = activity
        # system of a resource id: from evidence if known, else the activity target
        sys_of = dict(zip(obs.resource_id, obs.system_id))
        worker = activity[activity.source_system == "deletion_worker"]
        for rid, s in zip(worker.resource_id, worker.target_system):
            sys_of.setdefault(rid, s)
        for rid, s in zip(activity.resource_id, activity.target_system):
            sys_of.setdefault(rid, s)
        self.sys_of = sys_of
        self.universe = obs[obs.resource_id != ""][["resource_id", "captured_at"]]
        self.named = obs[(obs.resource_id != "") & (obs.state != "REFERENCED")][
            ["system_id", "resource_id", "captured_at", "raw_snippet"]]

    def key(self, rid):
        return (self.sys_of.get(rid, ""), rid)

    def A(self, ident, case, worker_only=False):
        a = self.act[(self.act.event_time >= case.requested_at) & (self.act.event_time <= case.audit_at)]
        if worker_only:
            a = a[a.source_system == "deletion_worker"]
        return {self.key(r) for r in a.resource_id if r}

    def B(self, ident, case):
        tokens = linking.user_tokens(ident)
        a = self.act[(self.act.event_type == "LINK_RESOURCE_IDENTITY") & (self.act.event_time <= case.audit_at)]
        return {self.key(r) for r, d in zip(a.resource_id, a.details)
                if tokens & {t.lower() if "@" in t else t for t in TOKEN.findall(d)}}

    def C(self, ident, case):
        return self.A(ident, case, worker_only=True)

    def D(self, ident, case):
        n = int(ident.user_id.split("_")[-1])
        ids = set(self.act[self.act.event_time <= case.audit_at].resource_id)
        ids |= set(self.universe[self.universe.captured_at <= case.audit_at].resource_id)
        out = set()
        for rid in ids:
            m = re.search(r"_(\d{1,3})$", rid)
            if m and int(m.group(1)) == n:
                out.add(self.key(rid))
        return out

    def N(self, ident, case):
        if not ident.name:
            return set()
        u = self.named[self.named.captured_at <= case.audit_at]
        hit = u[u.raw_snippet.str.contains(ident.name, regex=False)]
        return set(zip(hit.system_id, hit.resource_id))


def main():
    gold = score.gold_cases()
    pipe, _ = score.predict_samples()
    requests = loaders.load_sample_requests().set_index("case_id", drop=False)
    ch = Channels(pipe.obs, loaders.load_system_activity().fillna(""))
    allc, dev, held = score.split_ids(gold)
    obs = pipe.obs

    def activity_only(c, g):
        au = requests.audit_at[c]
        return {k for k in g if not ((obs.system_id == k[0]) & (obs.resource_id == k[1])
                                     & (obs.captured_at <= au)).any()}

    def run(ids, name):
        others_gold = {c: set().union(*(resources(gold[o][1]) for o in ids if o != c)) for c in ids}
        base = {c: set(pipe.trace.get(c, {}).get("linked", {})) for c in ids}
        g_all = {c: resources(gold[c][1]) for c in ids}
        ao = {c: activity_only(c, g_all[c]) - base[c] for c in ids}
        n_gold = sum(len(g) for g in g_all.values())
        n_ao = sum(len(v) for v in ao.values())
        tp0 = sum(len(g_all[c] & base[c]) for c in ids)
        p0 = sum(len(base[c]) for c in ids)
        print(f"{name}: gold={n_gold} activity-only gold={n_ao}")
        print(f"  {'chan':4s} {'recov':>6s} {'extra':>6s} {'xOther':>6s} {'recall':>7s} {'prec':>6s}"
              f" {'chanP':>6s} {'newG':>5s} {'newP':>6s}")
        print(f"  {'base':4s} {'-':>6s} {'-':>6s} {'-':>6s} {tp0 / n_gold:7.3f} {tp0 / max(p0, 1):6.3f}")
        for cname in "ABCDN":
            rec = extra = xother = tp = pn = newg = 0
            for c in ids:
                case = requests.loc[c]
                res = pipe.index.resolve_request(case)
                prop = getattr(ch, cname)(pipe.index.sets[res.user_id], case) if res.user_id else set()
                new = prop - base[c]
                rec += len(new & ao[c])
                newg += len(new & g_all[c])
                ex = new - g_all[c]
                extra += len(ex)
                xother += len(ex & others_gold[c])
                merged = base[c] | prop
                tp += len(merged & g_all[c])
                pn += len(merged)
            chan_p = rec / max(rec + extra, 1)
            print(f"  {cname:4s} {rec:6d} {extra:6d} {xother:6d} {tp / n_gold:7.3f} {tp / max(pn, 1):6.3f}"
                  f" {chan_p:6.3f} {newg:5d} {newg / max(newg + extra, 1):6.3f}")

    run(dev, "dev(22)")
    run(held, "held-out(10)")
    print("recov=activity-only gold newly linked; extra=new non-gold; xOther=extras that are "
          "other cases' gold (same split); chanP=recov/(recov+extra); newG=any gold newly linked; "
          "newP=newG/(newG+extra)")


def accounts():
    from ghost import account_finder
    gold = score.gold_cases()
    _, dev, held = score.split_ids(gold)
    main_mod = score.load_pipeline_module()
    pipe = main_mod.Pipeline(propagate_accounts=True, offline=True)
    pool = {c.case_id: c for c in pipe._account_pool(None)}
    gold_acct = {c: [s["resource_id"] for s in gold[c][1] if s["system_id"] == "account_service"][0]
                 for c in gold}
    need = {c for c in pool if not pool[c].account}
    f = pipe.finder

    def tally(picks, ids):
        ids = [c for c in ids if c in need]
        rec = sum(c in picks and picks[c][0] == gold_acct[c] for c in ids)
        wrong = sum(c in picks and picks[c][0] != gold_acct[c] for c in ids)
        return len(ids), rec, wrong, rec / max(rec + wrong, 1)

    kept = {c: p for c in need if (p := f.find(pool[c].ident, pool[c].reported_at, pool[c].audit_at))}
    print("account picks (cases needing one: picked correctly / wrong / precision)")
    for name, picks in [("kept finder", kept)] + [
            (f"propagation round {i}", {k: v for r in pipe.account_rounds[:i] for k, v in r.items()})
            for i in range(1, len(pipe.account_rounds) + 1)]:
        n518 = sum(c in picks for c in need if c not in gold)
        row = []
        for split, ids in (("dev", dev), ("held", held)):
            n, rec, wrong, prec = tally(picks, ids)
            row.append(f"{split} {rec}/{wrong}/{prec:.3f} (of {n})")
        print(f"  {name:22s} {' | '.join(row)} | 518 picks {n518}")
    picks = pipe.account_picks
    owner = {c.account: c.ident.user_id for c in pool.values() if c.account}
    for c, (rid, _) in sorted(picks.items()):
        owner.setdefault(rid, pool[c].ident.user_id)
    left = {c: f.survivors(pool[c].ident, pool[c].reported_at, pool[c].audit_at, owner)
            for c in need if c not in picks}
    amb = {c: v for c, v in left.items() if len(v) >= 2}
    print(f"after propagation: unresolved {len(left)} (>=2 candidates {len(amb)}, 1 candidate "
          f"{sum(len(v) == 1 for v in left.values())}, 0 candidates {sum(not v for v in left.values())});"
          f" 518 unresolved {sum(c not in gold for c in left)}, of which >=2 candidates "
          f"{sum(c not in gold for c in amb)}")
    print("forced pick (top-ranked candidate) on cases with >=2 candidates")
    print(f"  {'margin >=':>10s} {'dev ok/wrong/prec':>20s} {'held ok/wrong':>14s} {'518 rows':>9s}")
    ranked = {c: f.rank(v, pool[c].ident.user_id) for c, v in amb.items()}
    for margin in (0, 2, 5, 10, 20, 30):
        sel = {c: r for c, r in ranked.items() if r[1][1] - r[0][1] >= margin}
        out = []
        for ids in (dev, held):
            ok = sum(c in sel and sel[c][0][0] == gold_acct[c] for c in ids)
            bad = sum(c in sel and sel[c][0][0] != gold_acct[c] for c in ids)
            out.append((ok, bad))
        (dok, dbad), (hok, hbad) = out
        print(f"  {margin:>7d} min {dok:>6d}/{dbad}/{dok / max(dok + dbad, 1):.3f}       {hok:>4d}/{hbad}"
              f" {sum(c not in gold for c in sel):>12d}")
    in_pool = sum(gold_acct[c] in left[c] for c in dev if c in amb)
    print(f"  dev ambiguous cases whose gold account is among the candidates: {in_pool}/"
          f"{sum(c in amb for c in dev)}")


if __name__ == "__main__":
    accounts() if sys.argv[1:] == ["--accounts"] else main()
