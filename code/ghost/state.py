"""State of a resource at audit_at, its citation, and its category.

State = the state in the latest file (captured_at <= audit_at) that has a
stateful observation of the resource, or that is a covering snapshot of the
resource's system without the resource (a coverage row: resource_id "" and
the same system_id) -> ABSENT, cited to that snapshot. Within the chosen
file, any copy showing the data wins (replica drift: one PRESENT copy means
PRESENT). On a tie in captured_at, a real observation beats a coverage row.

Category = the most common non-empty category_hint of the resource's
observations up to audit_at, else a system_id fallback (counted).

planner_state() maps the observation vocabulary onto the planner's
(IDENTIFIABLE -> PRESENT, ...); impossible combinations are coerced to the
compliant state and counted.
"""
from collections import Counter, namedtuple

import pandas as pd

from . import planner

ResourceState = namedtuple("ResourceState", "state evidence_id copy")

# Within one file, the first state in this order wins ("any copy present").
SEVERITY = ("IDENTIFIABLE", "PRESENT", "ACTIVE", "REDACTED", "ANONYMIZED", "DISABLED",
            "BLOCKED", "ABSENT")
COVERAGE_KINDS = ("sql", "json")

CATEGORY_BY_SYSTEM = {
    "account_service": "USER_PROFILE", "search_service": "SEARCH_INDEX_ENTRY",
    "analytics_platform": "ANALYTICS_PROFILE", "support_platform": "SUPPORT_MESSAGE",
    "security_service": "SECURITY_AUDIT_LOG", "integration_service": "DATA_FLOW",
    "backup_service": "BACKUP_ARCHIVE", "export_service": "USER_EXPORT",
    "identity_service": "ACCOUNT_TOMBSTONE", "legal_service": "LEGAL_HOLD_RECORD",
    "marketing_platform": "MARKETING_PROFILE", "cache_service": "CACHE_ENTRY",
    "email_delivery_service": "EMAIL_DELIVERY_LOG",
}


def _ts(value):
    t = pd.Timestamp(value)
    return t.tz_localize("UTC") if t.tzinfo is None else t


class StateResolver:
    def __init__(self, obs):
        obs = obs.assign(_t=pd.to_datetime(obs.captured_at, utc=True))
        stateful = obs[(obs.resource_id != "") & ~obs.state.isin(["", "REFERENCED"])]
        self._by_resource = {k: g for k, g in stateful.groupby(["system_id", "resource_id"])}
        hinted = obs[obs.resource_id != ""]
        self._hints = {k: g for k, g in hinted.groupby(["system_id", "resource_id"])}
        cover = obs[(obs.resource_id == "") & (obs.system_id != "")
                    & obs.file_kind.isin(COVERAGE_KINDS)]
        self._coverage = {k: g.drop_duplicates("file_id") for k, g in cover.groupby("system_id")}
        self._files_of = {k: set(g.file_id) for k, g in hinted.groupby(["system_id", "resource_id"])}
        self.fallbacks = 0
        self.fallback_log = Counter()

    def resolve(self, system_id, resource_id, audit_at, allow_absence=True):
        """ResourceState at audit_at, or None when nothing stateful is known.

        allow_absence=False ignores coverage rows (used for retained records:
        a partial snapshot cannot prove a record that policy keeps is gone).
        """
        cutoff = _ts(audit_at)
        best_t, best = None, None
        own = self._by_resource.get((system_id, resource_id))
        if own is not None:
            own = own[own._t <= cutoff]
            if len(own):
                best_t = own._t.max()
                rows = own[own._t == best_t].sort_values("file_id")
                pick = min(rows.itertuples(), key=lambda r: (SEVERITY.index(r.state)
                                                              if r.state in SEVERITY else 99))
                best = ResourceState(pick.state, pick.file_id, pick.copy)
        cover = self._coverage.get(system_id) if allow_absence else None
        if cover is not None:
            seen = self._files_of.get((system_id, resource_id), set())
            cover = cover[(cover._t <= cutoff) & ~cover.file_id.isin(seen)]
            if len(cover):
                t = cover._t.max()
                if best_t is None or t > best_t:
                    f = cover[cover._t == t].sort_values("file_id").iloc[0]
                    best = ResourceState("ABSENT", f.file_id, f.copy)
        return best

    def category(self, system_id, resource_id, audit_at):
        rows = self._hints.get((system_id, resource_id))
        if rows is not None:
            rows = rows[(rows._t <= _ts(audit_at)) & (rows.category_hint != "")]
            if len(rows):
                counts = Counter(rows.category_hint)
                latest = rows.sort_values("_t").category_hint.iloc[-1]
                top = max(counts.values())
                return latest if counts[latest] == top else sorted(
                    c for c, n in counts.items() if n == top)[0]
        self.fallbacks += 1
        self.fallback_log[system_id] += 1
        return CATEGORY_BY_SYSTEM.get(system_id, "")


def planner_state(category, raw_state, treatments, coercions=None):
    """Observation state -> the planner's state for this category's treatment."""
    t = treatments[category]
    compliant = planner.STATE_OF[t.verification]
    finding = planner.STATE_OF[t.finding] if t.finding else None
    exposed = raw_state in ("IDENTIFIABLE", "PRESENT", "ACTIVE")
    if raw_state == compliant:
        return compliant
    if finding == "ACTIVE":                     # data flows / restore paths
        mapped = "ACTIVE" if exposed else compliant
    elif compliant == "ABSENT":                 # DELETE: any surviving copy is a remaining record
        mapped = "ABSENT" if raw_state == "ABSENT" else "PRESENT"
    elif compliant == "PRESENT":                # RETAIN
        mapped = "PRESENT"
    else:                                       # REDACT / ANONYMIZE
        mapped = "PRESENT" if exposed else compliant
    if coercions is not None and mapped == compliant and raw_state not in (compliant,) \
            and not (compliant == "PRESENT" and exposed):
        coercions[(category, raw_state)] += 1
    return mapped
