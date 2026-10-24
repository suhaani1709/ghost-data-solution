"""Ghost Data Still Exists - deletion-audit pipeline (baseline v0).

Per case: intent -> (NOT_APPLICABLE, []) or identity -> linking -> state ->
category -> planner.build_steps. PNG evidence is not used yet.

Run:  python3 code/main.py                       # 518 cases -> output.csv at the repo root
      python3 code/main.py --sample --out PATH   # the 32 public sample requests
"""
import argparse
import csv
import json
import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ghost import identity, intent, linking, loaders, observations, planner, state  # noqa: E402


class Pipeline:
    def __init__(self, dataset_dir=None):
        self.obs = observations.build_observations(dataset_dir)
        self.index = identity.IdentityIndex.from_dataset(dataset_dir)
        self.linker = linking.Linker(self.obs)
        self.resolver = state.StateResolver(self.obs)
        self.treatments = planner.load_treatments(loaders.load_deletion_rules(dataset_dir))
        self.stats = Counter()
        self.coercions = Counter()
        self.trace = {}   # case_id -> {"linked": {...}, "resources": [...]}

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
        resources = []
        for (system_id, resource_id) in linked:
            st = self.resolver.resolve(system_id, resource_id, case.audit_at)
            if st is None:
                self.stats["no_state"] += 1
                continue
            category = self.resolver.category(system_id, resource_id, case.audit_at)
            if category not in self.treatments:
                self.stats["unknown_category"] += 1
                continue
            pstate = state.planner_state(category, st.state, self.treatments, self.coercions)
            resources.append((system_id, resource_id, category, pstate, st.evidence_id))
        self.trace[case.case_id] = {"linked": linked, "resources": resources}
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
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.ERROR)
    requests = loaders.load_sample_requests() if args.sample else loaders.load_deletion_requests()
    out = Path(args.out) if args.out else loaders.REPO_ROOT / "output.csv"
    pipe = Pipeline()
    rows = pipe.run(requests)
    write_output(rows, out)
    print(f"wrote {len(rows)} rows -> {out}")
    print("status:", dict(Counter(r["deletion_status"] for r in rows)))
    print("stats:", dict(pipe.stats), "| category fallbacks:", pipe.resolver.fallbacks,
          "| state coercions:", sum(pipe.coercions.values()))


if __name__ == "__main__":
    main()
