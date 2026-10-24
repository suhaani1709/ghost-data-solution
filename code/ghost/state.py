"""State of a resource at audit_at, its citation, and its category.

State = the state in the latest file (captured_at <= audit_at) that has a
stateful observation of the resource, or that is a covering snapshot of the
resource's system without the resource (a coverage row: resource_id "" and
the same system_id) -> ABSENT, cited to that snapshot. Within the chosen
file, any copy showing the data wins (replica drift: one PRESENT copy means
PRESENT); the same holds across files of the same captured_at. On a tie in
captured_at, a real observation beats a coverage row.

Replica drift (replica_persist="drift", default): when the latest file that
captures a replica copy of the system (<= audit_at) holds the resource in a
replica copy with exposed data while that file's primary copy of the system
lacks it or holds it compliant, the resource stays PRESENT, cited to that
file, even if a later snapshot that does not capture the replica (e.g. a
primary-only inventory) shows it absent or redacted. A later replica capture
of the system without the row, or with it compliant, ends this.
"any" drops the primary-side condition; "off" disables the rule.

Category = the most common non-empty category_hint of the resource's
observations up to audit_at. Without a hint, the treatment operation the
deletion workflow ran on the resource (DELETE_RECORD / REDACT_RECORD /
ANONYMIZE_RECORD activity rows, event_time <= audit_at; the reported result
is ignored) picks the category, among those the system is seen to hold,
whose deletion_rules action matches; only when this is unambiguous
(counted as activity_categories). Else a system_id fallback (counted).

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
EXPOSED = ("IDENTIFIABLE", "PRESENT", "ACTIVE")
REPLICA_PERSIST = ("off", "any", "drift")
ACTION_OF_OPERATION = {"DELETE_RECORD": "DELETE", "REDACT_RECORD": "REDACT",
                       "ANONYMIZE_RECORD": "ANONYMIZE"}

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
    def __init__(self, obs, replica_persist="drift", activity=None, actions=None):
        if replica_persist not in REPLICA_PERSIST:
            raise ValueError(f"replica_persist must be one of {REPLICA_PERSIST}")
        self.replica_persist = replica_persist
        obs = obs.assign(_t=pd.to_datetime(obs.captured_at, utc=True),
                         _e=pd.to_datetime(obs.event_time.where(obs.event_time != ""),
                                           utc=True, errors="coerce"))
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
        self.replica_holds = 0
        self.activity_categories = 0
        # system -> categories it is seen to hold; (system, resource) -> [(time, action)].
        self._system_categories = {k: sorted(set(g.category_hint) - {""})
                                   for k, g in hinted.groupby("system_id")}
        self._actions = actions or {}
        self._treatment_ops = {}
        if activity is not None and len(activity) and self._actions:
            ops = activity[activity.event_type.isin(ACTION_OF_OPERATION)]
            for t, s_, r, e in zip(pd.to_datetime(ops.event_time, utc=True), ops.target_system,
                                   ops.resource_id, ops.event_type):
                self._treatment_ops.setdefault((s_, r), []).append((t, ACTION_OF_OPERATION[e]))
        # (file_id, system_id, copy) -> {resource_id: [states]}; system -> replica-capturing files.
        self._copies = {}
        for f, s_, c, r, st in zip(stateful.file_id, stateful.system_id, stateful["copy"],
                                   stateful.resource_id, stateful.state):
            self._copies.setdefault((f, s_, c), {}).setdefault(r, []).append(st)
        rep = stateful[stateful["copy"] == "replica"]
        self._replica_files = {k: g.drop_duplicates("file_id")[["file_id", "_t"]]
                               for k, g in rep.groupby("system_id")}

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
                    best_t = t
        if best is not None and best.state not in EXPOSED and self.replica_persist != "off":
            hold = self._replica_hold(system_id, resource_id, cutoff)
            if hold is not None and hold[0] < best_t:
                self.replica_holds += 1
                best = hold[1]
        return best

    def resolve_late(self, system_id, resource_id, audit_at, kinds=("log",)):
        """(state, category_hint) from observations in files captured *after* audit_at whose own
        event_time is <= audit_at (latest event wins; on a tie any exposed copy wins), or None.
        Used only for late-linked resources; the caller must not cite these files."""
        cutoff = _ts(audit_at)
        rows = self._hints.get((system_id, resource_id))
        if rows is None:
            return None
        rows = rows[(rows._t > cutoff) & rows.file_kind.isin(kinds) & rows._e.notna()
                    & (rows._e <= cutoff)]
        hints = sorted(set(rows.category_hint) - {""})
        rows = rows[~rows.state.isin(["", "REFERENCED"])]
        if not len(rows):
            return None
        latest = rows[rows._e == rows._e.max()]
        pick = min(latest.state, key=lambda st: SEVERITY.index(st) if st in SEVERITY else 99)
        return pick, (hints[0] if len(hints) == 1 else "")

    def _replica_hold(self, system_id, resource_id, cutoff):
        """(captured_at, ResourceState) when the latest replica capture of the system holds the
        resource exposed in a replica copy (and, mode "drift", its primary copy does not)."""
        files = self._replica_files.get(system_id)
        if files is None:
            return None
        files = files[files._t <= cutoff]
        if not len(files):
            return None
        t = files._t.max()
        for f in sorted(files[files._t == t].file_id):
            held = self._copies[(f, system_id, "replica")].get(resource_id, [])
            if not any(st in EXPOSED for st in held):
                continue
            if self.replica_persist == "drift":
                primary = self._copies.get((f, system_id, "primary"))
                if not primary or any(st in EXPOSED for st in primary.get(resource_id, [])):
                    continue
            return t, ResourceState("PRESENT", f, "replica")
        return None

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
        cutoff = _ts(audit_at)
        done = {a for t, a in self._treatment_ops.get((system_id, resource_id), ()) if t <= cutoff}
        if len(done) == 1:
            cands = [c for c in self._system_categories.get(system_id, ())
                     if self._actions.get(c) in done]
            if len(cands) == 1:
                self.activity_categories += 1
                return cands[0]
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
