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

    def find(self, ident, reported_at, audit_at):
        """(resource_id, activity_id of its delete row) or None."""
        reported, cutoff = pd.Timestamp(reported_at), pd.Timestamp(audit_at)
        d = self._deletes
        d = d[(d._t >= reported - self.before) & (d._t <= reported + self.after) & (d._t <= cutoff)]
        mine = linking.user_tokens(ident)
        survivors = {}
        for rid, aid in zip(d.resource_id, d.activity_id):
            if rid not in survivors and not self._tied_elsewhere(rid, mine, cutoff):
                survivors[rid] = aid
        if len(survivors) > 1:
            n = _number(ident.user_id)
            survivors = {r: a for r, a in survivors.items() if _number(r) == n}
        if len(survivors) != 1:
            return None
        (rid, aid), = survivors.items()
        return rid, aid
