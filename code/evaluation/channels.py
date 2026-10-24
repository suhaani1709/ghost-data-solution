"""Diagnostic: which activity channel could link gold resources that never
appear in parsed text evidence (diagnosis only, the pipeline is untouched).

Run:  python3 code/evaluation/channels.py

Each channel, alone, proposes (system_id, resource_id) pairs for a case on
top of the pipeline's evidence-linked set L:
  A  any activity row with requested_at <= event_time <= audit_at
  B  LINK_RESOURCE_IDENTITY rows (<= audit_at) naming one of the user's tokens
  C  A restricted to source_system == deletion_worker
  D  resource-number convention: resource suffix (<= 3 digits) == user number
Reported on dev(22): activity-only gold recovered, extra (wrong) resources
added, resulting linkage recall / precision, extras that are other dev
cases' gold resources. Held-out(10): aggregates only.
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
              f" {'chanP':>6s}")
        print(f"  {'base':4s} {'-':>6s} {'-':>6s} {'-':>6s} {tp0 / n_gold:7.3f} {tp0 / max(p0, 1):6.3f}")
        for cname in "ABCD":
            rec = extra = xother = tp = pn = 0
            for c in ids:
                case = requests.loc[c]
                res = pipe.index.resolve_request(case)
                prop = getattr(ch, cname)(pipe.index.sets[res.user_id], case) if res.user_id else set()
                new = prop - base[c]
                rec += len(new & ao[c])
                ex = new - g_all[c]
                extra += len(ex)
                xother += len(ex & others_gold[c])
                merged = base[c] | prop
                tp += len(merged & g_all[c])
                pn += len(merged)
            chan_p = rec / max(rec + extra, 1)
            print(f"  {cname:4s} {rec:6d} {extra:6d} {xother:6d} {tp / n_gold:7.3f} {tp / max(pn, 1):6.3f}"
                  f" {chan_p:6.3f}")

    run(dev, "dev(22)")
    run(held, "held-out(10)")
    print("recov=activity-only gold newly linked; extra=new non-gold; xOther=extras that are "
          "other cases' gold (same split); chanP=recov/(recov+extra)")


if __name__ == "__main__":
    main()
