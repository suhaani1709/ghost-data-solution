"""Resource <-> user linking: exact identifier matching, plus optional
one-hop reference following.

A resource links to a user when an observation (evidence unit) of that
resource also carries any token of the user's IdentitySet: user_id, every
current/historical email, the SHA-256 of every email, every phone. Names are
not used yet (units do not say whose name they show).

Only observations from files captured at or before audit_at count (any_time=True:
identifier matches from every file count, since who owns a record does not change;
reference following stays <= audit_at; state is never read here). Linking
is sticky: one qualifying observation is enough, later observations with
nulled identifiers do not undo it. REFERENCED rows (an id merely mentioned by
another record) never link by themselves.

follow=True adds one hop, starting only from resources linked above: an id
REFERENCED by a unit of a linked resource (e.g. source_resource_id), and an
id named in the details of an activity row whose resource_id is linked (e.g.
"repopulated downstream resource ..."), both captured <= audit_at. Followed
resources are never followed again.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Optional

import pandas as pd

from . import parse_common

# Activity details end ids with "." so parse_common.RESOURCE_ID (no trailing dot) misses them.
ACTIVITY_REF = re.compile(r"\b(?:%s)_\d+\b" % "|".join(parse_common.RESOURCE_PREFIXES))


def user_tokens(ident) -> set[str]:
    tokens = {ident.user_id} | set(ident.emails) | {h.lower() for h in ident.email_hashes} \
        | set(ident.phones)
    return {t for t in tokens if t}


def _utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True)


class Linker:
    def __init__(self, obs: pd.DataFrame, activity: Optional[pd.DataFrame] = None, follow: bool = False) -> None:
        usable = obs[(obs.resource_id != "") & (obs.state != "REFERENCED")]
        self._captured = _utc(usable.captured_at)
        self._index = defaultdict(list)    # token -> [row label]
        self._rows = usable
        for label, ids in zip(usable.index, usable.identifiers):
            for values in ids.values():
                for v in values:
                    self._index[v].append(label)
        self.follow = follow
        self._refs = defaultdict(list)     # owner resource_id -> [(time, source id, key)]
        if not follow:
            return
        if "referenced_by" in obs:
            ref = obs[(obs.state == "REFERENCED") & (obs.referenced_by.fillna("") != "")]
            for t, f, s, r, owners in zip(_utc(ref.captured_at), ref.file_id, ref.system_id,
                                          ref.resource_id, ref.referenced_by):
                for owner in owners.split():
                    self._refs[owner].append((t, f, (s, r)))
        if activity is not None and len(activity):
            for t, aid, rid, target, details in zip(_utc(activity.event_time), activity.activity_id,
                                                    activity.resource_id, activity.target_system,
                                                    activity.details.fillna("")):
                for other in sorted(set(ACTIVITY_REF.findall(details)) - {rid}):
                    self._refs[rid].append(
                        (t, aid, (parse_common.system_for(other, target), other)))

    def link(self, ident, audit_at: str, any_time: bool = False) -> dict[tuple[str, str], list[str]]:
        """{(system_id, resource_id): [file_id / activity_id, ...] that linked it} at audit_at."""
        cutoff = pd.Timestamp(audit_at)
        cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff
        out = {}
        for token in sorted(user_tokens(ident)):
            for label in self._index.get(token, ()):
                if self._captured[label] > cutoff and not any_time:
                    continue
                row = self._rows.loc[label]
                files = out.setdefault((row.system_id, row.resource_id), [])
                if row.file_id not in files:
                    files.append(row.file_id)
        if self.follow:
            followed = {}
            for (_, rid) in sorted(out):
                for t, source, key in self._refs.get(rid, ()):
                    if t <= cutoff and key not in out:
                        sources = followed.setdefault(key, [])
                        if source not in sources:
                            sources.append(source)
            out.update(followed)
        return {k: sorted(v) for k, v in sorted(out.items())}
