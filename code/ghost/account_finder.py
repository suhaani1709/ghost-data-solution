"""Account finder: the subject's account_service record when linking found none.

Every sample case has exactly one account_service resource. When exact
linking already found one, nothing changes. Otherwise the candidates are
account_service DELETE_RECORD activity rows whose event_time falls in
[reported_at - before, reported_at + after] and <= audit_at (the deletion
worker deletes the account shortly before the workflow reports; on dev-22 the
gold account's delete lies 70 min before to 8 min after reported_at).

A candidate is removed when evidence captured <= audit_at (a unit of that
account, not a REFERENCED mention) carries any identifier that is not one of
the subject's tokens: the evidence ties it to someone else. Activity claims
never remove or confirm a candidate. Among the survivors, one survivor is
chosen; with several, the user-number pattern (account number == user
number) breaks the tie only if exactly one survivor matches. Otherwise
nothing is chosen.

The same finder runs for another system and worker operation by parameter
(system=, events=; e.g. analytics_platform / ANONYMIZE_RECORD, the
"same-batch" idea). Only the account rule (one per case) is backed by every
sample; other systems must be measured before use.
"""
from __future__ import annotations

import re
from collections import namedtuple
from typing import Any, Optional

import pandas as pd

from . import linking

NUMBER = re.compile(r"_(\d+)$")


STATUS_RESULT = {"COMPLETE": "SUCCESS", "PARTIALLY_COMPLETE": "PARTIAL", "NOT_STARTED": "FAILED"}


def newest_account(linked: dict, linked_before_audit: dict, captured: dict[str, str], audit_at: str) -> dict:
    """Every case has exactly one account (gold 32/32). When evidence links several accounts to the
    subject, keep the account whose linking evidence (captured <= audit_at) is newest: a user who
    deleted an old account and later signed up again is audited on the account current at audit_at.
    If no account is linked before audit_at, the newest any-date link is kept. Other records untouched."""
    accounts = [k for k in linked if k[0] == "account_service"]
    if len(accounts) < 2:
        return linked
    def newest(k, pre):
        times = [captured.get(f, "") for f in linked.get(k, []) if f in captured]
        times = [t for t in times if t <= audit_at] if pre else times
        return max(times, default="")
    pre = [k for k in accounts if k in linked_before_audit]
    pool = pre or accounts
    keep = max(pool, key=lambda k: (newest(k, bool(pre)), k[1]))
    return {k: v for k, v in linked.items() if k[0] != "account_service" or k == keep}


def needs(linked: dict, system: str) -> bool:
    """True when linking found no resource of this system."""
    return not any(s == system for s, _ in linked)


def one_account(linked: dict, linked_before_audit: dict) -> dict:
    """Every case has one account (gold 32/32). When evidence up to audit_at already links an
    account, accounts linked only by later evidence (e.g. a new sign-up after the deletion) are
    not this case's record and are removed. Other records are untouched."""
    early = {k for k in linked_before_audit if k[0] == "account_service"}
    if not early:
        return linked
    return {k: v for k, v in linked.items() if k[0] != "account_service" or k in early}


def needs_account(linked: dict) -> bool:
    return needs(linked, "account_service")


def _number(resource_id: str) -> Optional[int]:
    m = NUMBER.search(resource_id)
    return int(m.group(1)) if m else None


class AccountFinder:
    def __init__(self, obs, activity, before_min=75, after_min=10, system="account_service",
                 events=("DELETE_RECORD",), windows=None, status_match=False, status_windows=None):
        # status_windows=N: apply the status match only in the first N windows (None = all).
        self.status_windows = status_windows
        # status_match: the delete event's reported_result must match the request's
        # reported_status (COMPLETE~SUCCESS, PARTIALLY_COMPLETE~PARTIAL, NOT_STARTED~FAILED;
        # 256 of 261 labelled pairs agree). Requests without a status are not filtered.
        self.status_match = status_match
        # windows: ((minutes before reported_at, minutes after reported_at), ...), tried in order: the
        # first window holding any surviving candidate decides. A negative "after" ends the window
        # before reported_at. Default: the single window (before_min, after_min).
        self.windows = [(pd.Timedelta(minutes=b), pd.Timedelta(minutes=a))
                        for b, a in (windows or ((before_min, after_min),))]
        d = activity[activity.event_type.isin(events) & (activity.target_system == system)]
        self._deletes = d.assign(_t=pd.to_datetime(d.event_time, utc=True)).sort_values(
            ["_t", "activity_id"])
        units = obs[(obs.system_id == system) & (obs.resource_id != "")
                    & (obs.state != "REFERENCED")]
        self._tokens = {}   # resource_id -> [(captured_at, set of identifier tokens)]
        for rid, t, ident in zip(units.resource_id, pd.to_datetime(units.captured_at, utc=True),
                                 units.identifiers):
            tokens = {v for values in ident.values() for v in values}
            if tokens:
                self._tokens.setdefault(rid, []).append((t, tokens))

    def _tied_elsewhere(self, resource_id, mine, cutoff):
        return any(t <= cutoff and tokens - mine for t, tokens in self._tokens.get(resource_id, ()))

    def survivors(self, ident: Any, reported_at: str, audit_at: str, taken: Optional[dict[str, str]] = None,
                  reported_status: Optional[str] = None) -> dict[str, tuple[str, float]]:
        """{resource_id: (activity_id of its first delete row in the window, minutes from
        reported_at of its closest one)} after removing accounts tied elsewhere and accounts
        that `taken` ({resource_id: user_id}) assigns to another user."""
        reported, cutoff = pd.Timestamp(reported_at), pd.Timestamp(audit_at)
        mine = linking.user_tokens(ident)
        taken = taken or {}
        out = {}
        for i, (before, after) in enumerate(self.windows):
            use_status = self.status_windows is None or i < self.status_windows
            out = self._window(ident, reported, cutoff, before, after, mine, taken,
                               reported_status if use_status else None)
            if out:
                break
        return out

    def _window(self, ident, reported, cutoff, before, after, mine, taken, reported_status=None):
        d = self._deletes
        d = d[(d._t >= reported - before) & (d._t <= reported + after) & (d._t <= cutoff)]
        want = STATUS_RESULT.get(reported_status) if self.status_match else None
        if want is not None:
            d = d[d.reported_result == want]
        out = {}
        for rid, aid, t in zip(d.resource_id, d.activity_id, d._t):
            if taken.get(rid, ident.user_id) != ident.user_id:
                continue
            minutes = abs((t - reported).total_seconds()) / 60
            if rid in out:
                out[rid] = (out[rid][0], min(out[rid][1], minutes))
            elif not self._tied_elsewhere(rid, mine, cutoff):
                out[rid] = (aid, minutes)
        return out

    @staticmethod
    def decide(survivors: dict[str, tuple[str, float]], user_id: str) -> Optional[tuple[str, str]]:
        """The one survivor, else the one survivor with the user's number, else None."""
        if len(survivors) > 1:
            n = _number(user_id)
            survivors = {r: v for r, v in survivors.items() if _number(r) == n}
        if len(survivors) != 1:
            return None
        (rid, (aid, _)), = survivors.items()
        return rid, aid

    @staticmethod
    def rank(survivors: dict[str, tuple[str, float]], user_id: str) -> list[tuple[str, float]]:
        """[(resource_id, minutes from reported_at)], closest first, then the user-number
        pattern, then resource_id. Measurement only (forced pick, not used by the pipeline)."""
        n = _number(user_id)
        return [(r, m) for r, (_, m) in sorted(
            survivors.items(), key=lambda kv: (kv[1][1], _number(kv[0]) != n, kv[0]))]

    def find(self, ident: Any, reported_at: str, audit_at: str,
             reported_status: Optional[str] = None) -> Optional[tuple[str, str]]:
        """(resource_id, activity_id of its delete row) or None."""
        return self.decide(self.survivors(ident, reported_at, audit_at, reported_status=reported_status),
                           ident.user_id)


PoolCase = namedtuple("PoolCase", "case_id ident reported_at audit_at account reported_status",
                      defaults=(None,))


def propagate(cases: list[PoolCase], finder: AccountFinder) -> tuple[dict[str, tuple[str, str]], list[dict]]:
    """Constraint propagation over every known request (PoolCase rows).

    An account belongs to exactly one user. Accounts that evidence links to a case's
    user (PoolCase.account) start as taken. Each round decides every unresolved case
    (finder.decide on its survivors, taken accounts of other users removed); when two
    users pick the same account in one round, neither gets it. Picks are final.
    Repeats until a round resolves nothing.

    Returns (picks {case_id: (resource_id, activity_id)}, rounds [{case_id: pick}]).
    """
    owner = {}
    for c in sorted(cases, key=lambda c: c.case_id):
        if c.account:
            owner.setdefault(c.account, c.ident.user_id)
    pending = sorted((c for c in cases if not c.account), key=lambda c: c.case_id)
    picks, rounds = {}, []
    while True:
        decided = {}
        for c in pending:
            if c.case_id in picks:
                continue
            pick = finder.decide(finder.survivors(c.ident, c.reported_at, c.audit_at, owner,
                                                  c.reported_status), c.ident.user_id)
            if pick is not None:
                decided[c.case_id] = (c.ident.user_id, pick)
        users = {}
        for uid, (rid, _) in decided.values():
            users.setdefault(rid, set()).add(uid)
        done = {cid: pick for cid, (uid, pick) in decided.items() if len(users[pick[0]]) == 1}
        if not done:
            return picks, rounds
        for cid, (rid, _) in done.items():
            owner[rid] = decided[cid][0]
        picks.update(done)
        rounds.append(done)
