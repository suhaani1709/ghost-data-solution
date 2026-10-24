"""Ghost Data Still Exists - deletion-audit pipeline (baseline v0).

Per case: intent -> (NOT_APPLICABLE, []) or identity -> linking -> state ->
category -> planner.build_steps. Linking follows one reference hop from
linked resources; PNG evidence comes from code/image_transcripts.md.

Run:  python3 code/main.py                       # 518 cases -> output.csv at the repo root
      python3 code/main.py --sample --out PATH   # the 32 public sample requests
      python3 code/main.py --dataset DIR --out PATH   # another dataset/ layout (own cases)
"""
import argparse
import csv
import json
import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ghost import account_finder, identity, intent, linking, loaders, observations, planner, state  # noqa: E402


class Pipeline:
    def __init__(self, dataset_dir=None, follow_refs=True, images=True, replica_persist="drift",
                 activity_category=True, find_account=True, table_coverage=True,
                 propagate_accounts=True):
        self.obs = observations.build_observations(dataset_dir, images=images,
                                                   table_coverage=table_coverage)
        self.index = identity.IdentityIndex.from_dataset(dataset_dir)
        activity = loaders.load_system_activity(dataset_dir)
        rules = loaders.load_deletion_rules(dataset_dir)
        self.linker = linking.Linker(self.obs, activity=activity if follow_refs else None,
                                     follow=follow_refs)
        self.resolver = state.StateResolver(
            self.obs, replica_persist=replica_persist,
            activity=activity if activity_category else None,
            actions=dict(zip(rules.data_category, rules.required_action)))
        self.treatments = planner.load_treatments(rules)
        self.finder = account_finder.AccountFinder(self.obs, activity) if find_account else None
        self.account_picks, self.account_rounds = None, []
        if self.finder is not None and propagate_accounts:
            self.account_picks, self.account_rounds = account_finder.propagate(
                self._account_pool(dataset_dir), self.finder)
        self.stats = Counter()
        self.coercions = Counter()
        self.trace = {}   # case_id -> {"linked": {...}, "resources": [...]}

    def _account_pool(self, dataset_dir):
        """PoolCase for every deletion request in the dataset (evaluation + sample files)."""
        frames = [loaders.load_deletion_requests(dataset_dir)]
        try:
            frames.append(loaders.load_sample_requests(dataset_dir))
        except FileNotFoundError:
            pass
        pool = []
        for frame in frames:
            for case in frame.itertuples(index=False):
                uid = self.index.resolve_request(case).user_id
                if uid is None or intent.effective_intent(case.request_text, warn=False) == intent.NON_DELETE:
                    continue
                ident = self.index.sets[uid]
                accounts = [r for s, r in self.linker.link(ident, case.audit_at) if s == "account_service"]
                pool.append(account_finder.PoolCase(case.case_id, ident, case.reported_at,
                                                    case.audit_at, accounts[0] if accounts else None))
        return pool

    def run_case(self, case):
        if intent.effective_intent(case.request_text) == intent.NON_DELETE:
            self.stats["not_applicable"] += 1
            return "NOT_APPLICABLE", []
        res = self.index.resolve_request(case)
        if res.user_id is None:
            self.stats["unresolved_identity"] += 1
            linked = {}
        else:
            linked = self.linker.link(self.index.sets[res.user_id], case.audit_at)
            if self.finder is not None and account_finder.needs_account(linked):
                if self.account_picks is not None:
                    pick = self.account_picks.get(case.case_id)
                else:
                    pick = self.finder.find(self.index.sets[res.user_id], case.reported_at,
                                            case.audit_at)
                if pick is not None:
                    self.stats["account_found"] += 1
                    linked = dict(sorted({**linked, ("account_service", pick[0]): [pick[1]]}.items()))
        resources = []
        for (system_id, resource_id) in linked:
            category = self.resolver.category(system_id, resource_id, case.audit_at)
            if category not in self.treatments:
                self.stats["unknown_category"] += 1
                continue
            retained = self.treatments[category].verification == "VERIFY_RECORD_PRESENT"
            st = self.resolver.resolve(system_id, resource_id, case.audit_at,
                                       allow_absence=not retained)
            if st is None:
                self.stats["no_state"] += 1
                continue
            pstate = state.planner_state(category, st.state, self.treatments, self.coercions)
            resources.append((system_id, resource_id, category, pstate, st.evidence_id))
        self.trace[case.case_id] = {"linked": linked, "resources": resources}
        if planner.is_zero_link(resources):
            self.stats["zero_link_complete"] += 1
        return planner.build_steps(resources, self.treatments)

    def run(self, requests):
        rows = []
        for case in requests.sort_values("case_id").itertuples(index=False):
            status, steps = self.run_case(case)
            rows.append({"case_id": case.case_id, "deletion_status": status,
                         "steps_json": dumps(steps)})
        return rows


def dumps(steps):
    return json.dumps(steps, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def write_output(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=loaders.OUTPUT_COLUMNS)
        w.writeheader()
        w.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sample", action="store_true", help="run the 32 sample requests")
    ap.add_argument("--out", default=None, help="output CSV (default: repo-root output.csv)")
    ap.add_argument("--dataset", default=None, help="dataset directory (default: repo-root dataset/)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    load = loaders.load_sample_requests if args.sample else loaders.load_deletion_requests
    requests = load(args.dataset)
    out = Path(args.out) if args.out else loaders.REPO_ROOT / "output.csv"
    pipe = Pipeline(dataset_dir=args.dataset)
    rows = pipe.run(requests)
    write_output(rows, out)
    print(f"wrote {len(rows)} rows -> {out}")
    print("status:", dict(Counter(r["deletion_status"] for r in rows)))
    print("stats:", dict(pipe.stats), "| category fallbacks:", pipe.resolver.fallbacks,
          "| activity categories:", pipe.resolver.activity_categories,
          "| state coercions:", sum(pipe.coercions.values()))


if __name__ == "__main__":
    main()
