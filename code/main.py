"""Ghost Data Still Exists - deletion-audit agent.

Two LLM agents (OpenRouter free models, answers cached in code/llm_cache/):
the intent agent reads every request text, and the vision agent reads every
PNG screenshot. Both are cross-checked by deterministic rules (ghost/intent_agent.py,
ghost/vision_agent.py). Then, per case: intent -> (NOT_APPLICABLE, []) or
identity -> linking -> account finder -> state -> category -> planner.build_steps.

Run:  python3 code/main.py                       # 518 cases -> output.csv at the repo root
      python3 code/main.py --offline             # cached model answers only, never call the API
      python3 code/main.py --no-llm              # deterministic rules only
      python3 code/main.py --sample --out PATH   # the 32 public sample requests
      python3 code/main.py --dataset DIR --out PATH   # another dataset/ layout (own cases)
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ghost import (account_finder, identity, intent, intent_agent, investigator, linking,  # noqa: E402
                   llm, loaders, observations, parse_images, planner, state, vision_agent)

INVESTIGATOR_ALLOW = frozenset({"add_account", "drop", "recategorize"})


class Pipeline:
    def __init__(self, dataset_dir=None, follow_refs=True, images=True, replica_persist="drift",
                 activity_category=True, find_account=True, table_coverage=True,
                 propagate_accounts=True, use_llm=True, offline=False, link_after_audit=True,
                 explicit_absence=True, investigate=False, investigator_model="sonnet",
                 investigate_allow=INVESTIGATOR_ALLOW, investigate_cases=None, backend="claude",
                 investigate_budget=None, finder_windows=((76, -39), (6, 6)), status_match=True,
                 coverage_only_if_unobserved=False, newest_account=True, status_windows=1,
                 scoped_bundles=False):
        self._subject = None
        self.newest_account = newest_account
        # investigate_budget=N: route the investigator to at most N cases that the engine flags
        # as uncertain (investigator.uncertainty_flags / route); None = investigate_cases or all.
        self.investigate_budget = investigate_budget
        self.routed = sorted(investigate_cases, key=loaders.case_sort_key) if investigate_cases else []
        self.link_after_audit = link_after_audit
        self.investigator = investigator.Investigator(
            llm.ClaudeCodeClient(model=investigator_model, offline=offline)) if investigate else None
        self.investigate_allow = set(investigate_allow)
        self.investigate_cases = set(investigate_cases) if investigate_cases is not None else None
        self.reviews = {}     # case_id -> investigator.Review
        self.index = identity.IdentityIndex.from_dataset(dataset_dir)
        # Model backend for the intent and vision agents: Claude via Claude Code (default) or
        # free OpenRouter models. Answers are cached per backend in code/llm_cache/.
        self.llm = self._agent_client(use_llm, backend, investigator_model, offline)
        self.vision_report = {}
        image_rows = self._read_images(dataset_dir) if (use_llm and images) else None
        self.obs = observations.build_observations(dataset_dir, images=images,
                                                   table_coverage=table_coverage,
                                                   image_rows=image_rows)
        texts = [t for f in self._request_frames(dataset_dir) for t in f.request_text]
        self.intents = intent_agent.IntentAgent(self.llm).prepare(texts if use_llm else [])
        activity = loaders.load_system_activity(dataset_dir)
        rules = loaders.load_deletion_rules(dataset_dir)
        self.activity, self.rules = activity, rules
        self.manifest = loaders.load_evidence_files(dataset_dir)
        self.captured = dict(zip(self.manifest.file_id, self.manifest.captured_at))
        self.linker = linking.Linker(self.obs, activity=activity if follow_refs else None,
                                     follow=follow_refs)
        self.resolver = state.StateResolver(
            self.obs, replica_persist=replica_persist,
            activity=activity if activity_category else None,
            actions=dict(zip(rules.data_category, rules.required_action)),
            explicit_absence=explicit_absence, category_any_time=link_after_audit,
            coverage_only_if_unobserved=coverage_only_if_unobserved, scoped_bundles=scoped_bundles)
        self.treatments = planner.load_treatments(rules)
        # Account deletes land 39-76 min before reported_at (backtest on 278 labelled accounts,
        # code/evaluation/account_backtest.py); the +-6 min window is a fallback for a few
        # "reported completed" events. A wider window catches the next hour's slot.
        self.finder = account_finder.AccountFinder(
            self.obs, activity, windows=finder_windows, status_match=status_match,
            status_windows=status_windows) if find_account else None
        self._assign_accounts(dataset_dir, propagate_accounts)
        self.stats = Counter()
        self.coercions = Counter()
        self.trace = {}   # case_id -> {"linked": {...}, "resources": [...]}

    @staticmethod
    def _agent_client(use_llm: bool, backend: str, model: str, offline: bool):
        """Model client for the intent and vision agents (None = rules only)."""
        if not use_llm:
            return None
        if backend == "claude":
            return llm.ClaudeCodeClient(model=model, offline=offline)
        return llm.Client(offline=offline)

    def _assign_accounts(self, dataset_dir, propagate_accounts: bool) -> None:
        """Account picks by exclusive propagation over every request, and the owner of every
        account known from evidence or a pick (used to keep the investigator's candidates honest)."""
        self.account_picks, self.account_rounds = None, []
        self.account_owner = {}   # account resource_id -> user_id (evidence links + finder picks)
        if self.finder is None or not propagate_accounts:
            return
        pool = self._account_pool(dataset_dir)
        self.account_picks, self.account_rounds = account_finder.propagate(pool, self.finder)
        by_case = {c.case_id: c for c in pool}
        for c in pool:
            if c.account:
                self.account_owner.setdefault(c.account, c.ident.user_id)
        for cid, (rid, _) in sorted(self.account_picks.items()):
            self.account_owner.setdefault(rid, by_case[cid].ident.user_id)

    @staticmethod
    def _request_frames(dataset_dir):
        """The evaluation requests, plus the sample requests when the dataset has them."""
        frames = [loaders.load_deletion_requests(dataset_dir)]
        try:
            frames.append(loaders.load_sample_requests(dataset_dir))
        except FileNotFoundError:
            pass
        return frames

    def _read_images(self, dataset_dir):
        """Vision agent over every PNG in the manifest -> {file name: transcript rows}."""
        root = Path(dataset_dir or loaders.DATASET_DIR)
        manifest = loaders.load_evidence_files(dataset_dir)
        paths = {Path(p).name: root / p for p in manifest.file_path if p.lower().endswith(".png")}
        if not paths:
            return None
        sets = self.index.sets.values()
        universe = ({e for s in sets for e in s.emails}, {p for s in sets for p in s.phones},
                    set(self.index.sets))
        rows, self.vision_report = vision_agent.read_images(
            paths, parse_images.transcript(), universe, self.llm)
        return rows

    def _account_pool(self, dataset_dir):
        """PoolCase for every deletion request in the dataset (evaluation + sample files)."""
        pool = []
        for frame in self._request_frames(dataset_dir):
            for case in frame.itertuples(index=False):
                uid = self.index.resolve_request(case).user_id
                if uid is None or self.intents.label(case.request_text) == intent.NON_DELETE:
                    continue
                ident = self.index.sets[uid]
                links = self.linker.link(ident, case.audit_at, any_time=self.link_after_audit)
                if self.link_after_audit:
                    before = self.linker.link(ident, case.audit_at)
                    links = account_finder.one_account(links, before)
                    if self.newest_account:
                        links = account_finder.newest_account(links, before, self.captured, case.audit_at)
                accounts = [r for s, r in links if s == "account_service"]
                pool.append(account_finder.PoolCase(case.case_id, ident, case.reported_at,
                                                    case.audit_at, accounts[0] if accounts else None,
                                                    case.reported_status))
        return pool

    def run_case(self, case) -> tuple[str, list[dict]]:
        if self.intents.label(case.request_text) == intent.NON_DELETE:
            self.stats["not_applicable"] += 1
            return "NOT_APPLICABLE", []
        res = self.index.resolve_request(case)
        self._subject = linking.user_tokens(self.index.sets[res.user_id]) if res.user_id else None
        if res.user_id is None:
            self.stats["unresolved_identity"] += 1
            linked = {}
        else:
            linked = self.linker.link(self.index.sets[res.user_id], case.audit_at,
                                      any_time=self.link_after_audit)
            if self.link_after_audit:
                before = self.linker.link(self.index.sets[res.user_id], case.audit_at)
                linked = account_finder.one_account(linked, before)
                if self.newest_account:
                    linked = account_finder.newest_account(linked, before, self.captured, case.audit_at)
            if self.finder is not None and account_finder.needs_account(linked):
                if self.account_picks is not None:
                    pick = self.account_picks.get(case.case_id)
                else:
                    pick = self.finder.find(self.index.sets[res.user_id], case.reported_at,
                                            case.audit_at, case.reported_status)
                if pick is not None:
                    self.stats["account_found"] += 1
                    linked = dict(sorted({**linked, ("account_service", pick[0]): [pick[1]]}.items()))
        resources = [e for e in (self._entry(s, r, case.audit_at) for s, r in linked) if e]
        if self.investigator is not None and res.user_id is not None and (
                self.investigate_cases is None or case.case_id in self.investigate_cases):
            ident = self.index.sets[res.user_id]
            tools = investigator.CaseTools(
                obs=self.obs, activity=self.activity, resolver=self.resolver, finder=self.finder,
                treatments=self.treatments, rules=self.rules, manifest=self.manifest, ident=ident,
                case=case, owner={a: u for a, u in self.account_owner.items() if u != ident.user_id})
            review = self.investigator.review(case, ident, linked, resources, tools)
            resources = investigator.merge(resources, review, tools, self._entry, self.treatments,
                                           self.investigate_allow)
            self.reviews[case.case_id] = review
            self.stats[f"investigator_{review.status}"] += 1
        self.trace[case.case_id] = {"linked": linked, "resources": resources}
        if planner.is_zero_link(resources):
            self.stats["zero_link_complete"] += 1
        return planner.build_steps_unproven(resources, self.treatments)

    def _entry(self, system_id, resource_id, audit_at, category=None):
        """(system_id, resource_id, category, planner state, evidence_id) at audit_at, or None."""
        category = category or self.resolver.category(system_id, resource_id, audit_at)
        if category not in self.treatments:
            self.stats["unknown_category"] += 1
            return None
        retained = self.treatments[category].verification == "VERIFY_RECORD_PRESENT"
        st = self.resolver.resolve(system_id, resource_id, audit_at, allow_absence=not retained,
                                   subject=self._subject)
        if st is None and retained and self.link_after_audit:
            # linked (possibly by later evidence) but no state <= audit_at: policy keeps it,
            # so it is a future VERIFY_RECORD_PRESENT check with no citation.
            self.stats["retained_unproven"] += 1
            st = state.ResourceState("PRESENT", "", "unknown")
        if st is None:
            self.stats["no_state"] += 1
            return None
        pstate = state.planner_state(category, st.state, self.treatments, self.coercions)
        return (system_id, resource_id, category, pstate, st.evidence_id)

    def run(self, requests: pd.DataFrame) -> list[dict]:
        rows = []
        ordered = requests.sort_values("case_id", key=lambda ids: ids.map(loaders.case_sort_key))
        if self.investigator is not None and self.investigate_cases is None and self.investigate_budget is not None:
            # Routing pass: engine only, then send the most uncertain cases to the investigator.
            agent, self.investigator = self.investigator, None
            for case in ordered.itertuples(index=False):
                self.run_case(case)
            flags = {cid: investigator.uncertainty_flags(t["linked"], t["resources"], self.obs)
                     for cid, t in self.trace.items()}
            self.routed = investigator.route(flags, self.investigate_budget)
            self.flag_counts = Counter(f for fs in flags.values() for f in fs)
            self.investigator, self.investigate_cases = agent, set(self.routed)
            self.stats, self.coercions, self.trace = Counter(), Counter(), {}
            self.resolver.fallbacks = self.resolver.activity_categories = 0
        for case in ordered.itertuples(index=False):
            status, steps = self.run_case(case)
            rows.append({"case_id": case.case_id, "deletion_status": status,
                         "steps_json": dumps(steps)})
        return rows


def dumps(steps: list[dict]) -> str:
    return json.dumps(steps, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def write_output(rows: list[dict], path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=loaders.OUTPUT_COLUMNS, lineterminator="\n")  # LF, like dataset/
        w.writeheader()
        w.writerows(rows)


def main(argv: Optional[list[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sample", action="store_true", help="run the 32 sample requests")
    ap.add_argument("--out", default=None, help="output CSV (default: repo-root output.csv)")
    ap.add_argument("--dataset", default=None, help="dataset directory (default: repo-root dataset/)")
    ap.add_argument("--offline", action="store_true",
                    help="never call a model: use cached answers if present, else the deterministic rules")
    ap.add_argument("--no-llm", action="store_true", help="deterministic rules only, no model")
    ap.add_argument("--backend", choices=("claude", "openrouter"), default="claude",
                    help="model backend for the intent and vision agents (default: claude)")
    ap.add_argument("--no-investigator", action="store_true", help="skip the investigator agent")
    ap.add_argument("--investigate-budget", type=int, default=20,
                    help="investigate at most N engine-flagged uncertain cases (default 20)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    load = loaders.load_sample_requests if args.sample else loaders.load_deletion_requests
    try:
        requests = load(args.dataset)
        missing = loaders.missing_evidence(args.dataset)
    except (OSError, ValueError) as e:      # absent dataset directory/file or a wrong CSV header
        print(f"ERROR: cannot read the dataset: {e}", file=sys.stderr)
        sys.exit(1)
    if missing:
        print(f"ERROR: {len(missing)} missing evidence file(s) listed in evidence_files.csv, e.g. "
              f"{', '.join(missing[:3])}; refusing to write an output from partial evidence.", file=sys.stderr)
        sys.exit(1)
    out = Path(args.out) if args.out else loaders.REPO_ROOT / "output.csv"
    offline = args.offline
    if not (offline or args.no_llm) and args.backend == "claude" and shutil.which("claude") is None:
        # No Claude Code on this machine: run offline instead of failing call by call.
        print("NOTE: Claude Code CLI not found on PATH; no model call is made. The agents use cached "
              "answers where present (code/llm_cache/) and otherwise the deterministic rules. "
              "Pass --offline to make this explicit.", file=sys.stderr)
        offline = True
    try:
        pipe = Pipeline(dataset_dir=args.dataset, use_llm=not args.no_llm, offline=offline,
                        backend=args.backend, investigate=not (args.no_llm or args.no_investigator),
                        investigate_budget=args.investigate_budget)
    except (OSError, ValueError) as e:
        print(f"ERROR: cannot load the dataset: {e}", file=sys.stderr)
        sys.exit(1)
    rows = pipe.run(requests)
    write_output(rows, out)
    print(f"wrote {len(rows)} rows -> {out}")
    print("status:", dict(Counter(r["deletion_status"] for r in rows)))
    print("stats:", dict(pipe.stats), "| category fallbacks:", pipe.resolver.fallbacks,
          "| activity categories:", pipe.resolver.activity_categories,
          "| state coercions:", sum(pipe.coercions.values()))
    print("intent decisions:", dict(pipe.intents.stats))
    if pipe.reviews:
        print("investigator: routed", len(pipe.routed), "| flags", dict(getattr(pipe, "flag_counts", {})),
              "| reviews", dict(Counter(r.status for r in pipe.reviews.values())),
              "| accepted", sum(len(r.accepted) for r in pipe.reviews.values()),
              "| rejected", sum(len(r.rejected) for r in pipe.reviews.values()))
    print("vision agent:", dict(Counter(r["status"] for r in pipe.vision_report.values())))
    if pipe.llm is not None:
        print("model calls (intent/vision):", {k: v for k, v in sorted(pipe.llm.usage.items())})
    if pipe.investigator is not None:
        print("model calls (investigator):",
              {k: v for k, v in sorted(pipe.investigator.client.usage.items())})


if __name__ == "__main__":
    main()
