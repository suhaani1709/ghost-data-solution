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
import re
from collections import namedtuple

import pandas as pd

from . import linking

NUMBER = re.compile(r"_(\d+)$")


def needs(linked, system):
    """True when linking found no resource of this system."""
    return not any(s == system for s, _ in linked)


def needs_account(linked):
    return needs(linked, "account_service")


def _number(resource_id):
    m = NUMBER.search(resource_id)
    return int(m.group(1)) if m else None


class AccountFinder:
    def __init__(self, obs, activity, before_min=75, after_min=10, system="account_service",
                 events=("DELETE_RECORD",)):
        self.before = pd.Timedelta(minutes=before_min)
        self.after = pd.Timedelta(minutes=after_min)
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

    def survivors(self, ident, reported_at, audit_at, taken=None):
        """{resource_id: (activity_id of its first delete row in the window, minutes from
        reported_at of its closest one)} after removing accounts tied elsewhere and accounts
        that `taken` ({resource_id: user_id}) assigns to another user."""
        reported, cutoff = pd.Timestamp(reported_at), pd.Timestamp(audit_at)
        d = self._deletes
        d = d[(d._t >= reported - self.before) & (d._t <= reported + self.after) & (d._t <= cutoff)]
        mine = linking.user_tokens(ident)
        taken = taken or {}
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
    def decide(survivors, user_id):
        """The one survivor, else the one survivor with the user's number, else None."""
        if len(survivors) > 1:
            n = _number(user_id)
            survivors = {r: v for r, v in survivors.items() if _number(r) == n}
        if len(survivors) != 1:
            return None
        (rid, (aid, _)), = survivors.items()
        return rid, aid

    @staticmethod
    def rank(survivors, user_id):
        """[(resource_id, minutes from reported_at)], closest first, then the user-number
        pattern, then resource_id. Measurement only (forced pick, not used by the pipeline)."""
        n = _number(user_id)
        return [(r, m) for r, (_, m) in sorted(
            survivors.items(), key=lambda kv: (kv[1][1], _number(kv[0]) != n, kv[0]))]

    def find(self, ident, reported_at, audit_at):
        """(resource_id, activity_id of its delete row) or None."""
        return self.decide(self.survivors(ident, reported_at, audit_at), ident.user_id)


PoolCase = namedtuple("PoolCase", "case_id ident reported_at audit_at account")


def propagate(cases, finder):
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
            pick = finder.decide(finder.survivors(c.ident, c.reported_at, c.audit_at, owner),
                                 c.ident.user_id)
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
