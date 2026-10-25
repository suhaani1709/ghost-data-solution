"""Backtest of account assignment (finder + exclusive propagation) on labelled accounts.

Run:  python3 code/evaluation/account_backtest.py

Labels: the account of every deletion request whose account is linked by evidence
(518 + samples) plus the 32 gold sample accounts. For each half (even / odd case
number), the half's labelled accounts are hidden: the case has no account, and the
account's own evidence tokens are removed from the finder, exactly like a real
account that only appears in an activity row. Assignment then runs over all 540
deletion requests. Precision = right picks / picks on the hidden half; recall =
right picks / hidden cases whose account has a delete event. Windows are chosen on
the "tune" half (even) and reported on the "held" half (odd).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import score  # noqa: E402
from ghost import account_finder  # noqa: E402

WINDOWS = [((75, 10),), ((76, -39),), ((76, -39), (6, 6))]   # windows are tried in order (fallback)


def labelled(pipe, pool, gold):
    lab = {c.case_id: c.account for c in pool if c.account}
    lab.update({c: [s["resource_id"] for s in gold[c][1] if s["system_id"] == "account_service"][0] for c in gold})
    return lab


def run(pipe, pool, labels, hide, window, status_match=False):
    finder = account_finder.AccountFinder(pipe.obs, pipe.activity, windows=window, status_match=status_match)
    hidden = {labels[c] for c in hide}
    finder._tokens = {r: v for r, v in finder._tokens.items() if r not in hidden}
    cases = [c._replace(account=None) if c.case_id in hide else c for c in pool]
    picks, rounds = account_finder.propagate(cases, finder)
    deletable = set(finder._deletes.resource_id)
    target = [c for c in hide if labels[c] in deletable]
    picked = [c for c in hide if c in picks]
    right = sum(picks[c][0] == labels[c] for c in picked)
    return right, len(picked), len(target)


def main() -> None:
    main_mod = score.load_pipeline_module()
    pipe = main_mod.Pipeline(offline=True)
    gold = score.gold_cases()
    pool = pipe._account_pool(None)
    labels = labelled(pipe, pool, gold)
    ids = {c.case_id for c in pool}
    halves = {"tune": [c for c in labels if c in ids and int(c.split("_")[1]) % 2 == 0],
              "held": [c for c in labels if c in ids and int(c.split("_")[1]) % 2 == 1]}
    print(f"labelled accounts: {len(labels)} (tune {len(halves['tune'])}, held {len(halves['held'])})")
    print(f"{'window (min vs reported_at)':28s} {'tune P / R (picks)':24s} {'held P / R (picks)':24s}")
    for w, sm in [(w, False) for w in WINDOWS] + [(WINDOWS[-1], True)]:
        out = []
        for h in ("tune", "held"):
            right, picked, target = run(pipe, pool, labels, set(halves[h]), w, sm)
            out.append(f"{right / max(picked, 1):.3f} / {right / max(target, 1):.3f} ({picked})")
        label = " + ".join(f"[-{b},{a:+d}]" for b, a in w) + (" +status" if sm else "")
        print(f"{label:28s} {out[0]:24s} {out[1]:24s}")


if __name__ == "__main__":
    main()
