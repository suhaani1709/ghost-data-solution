"""Ghost Data Still Exists - deletion-audit pipeline (baseline v0).

Per case: intent -> (NOT_APPLICABLE, []) or identity -> linking -> state ->
category -> planner.build_steps. Linking follows one reference hop from
linked resources; PNG evidence comes from code/image_transcripts.md.
Late links (log events / records dated <= audit_at in files exported after it) add only
compliant, citation-free verification steps to INCOMPLETE cases.

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

from ghost import identity, intent, linking, loaders, observations, planner, state  # noqa: E402


class Pipeline:
    def __init__(self, dataset_dir=None, follow_refs=True, images=True, replica_persist="drift",
                 activity_category=True, late_kinds=("log", "json", "sql", "txt")):
        self.obs = observations.build_observations(dataset_dir, images=images)
        self.index = identity.IdentityIndex.from_dataset(dataset_dir)
        activity = loaders.load_system_activity(dataset_dir)
        rules = loaders.load_deletion_rules(dataset_dir)
        self.late_kinds = tuple(late_kinds)
        self.linker = linking.Linker(self.obs, activity=activity if follow_refs else None,
                                     follow=follow_refs, late_kinds=self.late_kinds)
        self.resolver = state.StateResolver(
            self.obs, replica_persist=replica_persist,
            activity=activity if activity_category else None,
            actions=dict(zip(rules.data_category, rules.required_action)))
        self.treatments = planner.load_treatments(rules)
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
        late = self._late_resources(res.user_id, linked, case.audit_at)
        self.trace[case.case_id] = {"linked": linked, "resources": resources, "late": late}
        if planner.is_zero_link(resources):
            self.stats["zero_link_complete"] += 1
        status, steps = planner.build_steps(resources, self.treatments)
        if status == "INCOMPLETE" and late:
            # Verification of a compliant resource in an INCOMPLETE case carries evidence_id "",
            # so a late-exported file is used without being cited. Status cannot change.
            self.stats["late_resources"] += len(late)
            status, steps = planner.build_steps(resources + late, self.treatments)
        return status, steps

    def _late_resources(self, user_id, linked, audit_at):
        """Compliant resources linked only through late-exported log events (see linking.py)."""
        if user_id is None or not self.late_kinds:
            return []
        out = []
        found = self.linker.late_links(self.index.sets[user_id], audit_at, exclude=set(linked))
        for (system_id, resource_id) in found:
            late = self.resolver.resolve_late(system_id, resource_id, audit_at, self.late_kinds)
            if late is None:
                continue
            raw, hint = late
            category = hint or state.CATEGORY_BY_SYSTEM.get(system_id, "")
            if category not in self.treatments:
                continue
            compliant = planner.STATE_OF[self.treatments[category].verification]
            pstate = state.planner_state(category, raw, self.treatments)
            if pstate != compliant:
                self.stats["late_noncompliant_skipped"] += 1   # a finding would need a citation
                continue
            out.append((system_id, resource_id, category, pstate, ""))
        return out

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
