"""Resource <-> user linking, v0: exact identifier matching only.

A resource links to a user when an observation (evidence unit) of that
resource also carries any token of the user's IdentitySet: user_id, every
current/historical email, the SHA-256 of every email, every phone. Names are
not used yet (units do not say whose name they show).

Only observations from files captured at or before audit_at count. Linking
is sticky: one qualifying observation is enough, later observations with
nulled identifiers do not undo it. REFERENCED rows (an id merely mentioned by
another record) never link, and activity rows are not used at all.
"""
from collections import defaultdict

import pandas as pd


def user_tokens(ident):
    tokens = {ident.user_id} | set(ident.emails) | {h.lower() for h in ident.email_hashes} \
        | set(ident.phones)
    return {t for t in tokens if t}


class Linker:
    def __init__(self, obs):
        usable = obs[(obs.resource_id != "") & (obs.state != "REFERENCED")]
        self._captured = pd.to_datetime(usable.captured_at, utc=True)
        self._index = defaultdict(list)    # token -> [row label]
        self._rows = usable
        for label, ids in zip(usable.index, usable.identifiers):
            for values in ids.values():
                for v in values:
                    self._index[v].append(label)

    def link(self, ident, audit_at):
        """{(system_id, resource_id): [file_id, ...] that linked it} at audit_at."""
        cutoff = pd.Timestamp(audit_at)
        cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff
        out = {}
        for token in sorted(user_tokens(ident)):
            for label in self._index.get(token, ()):
                if self._captured[label] > cutoff:
                    continue
                row = self._rows.loc[label]
                files = out.setdefault((row.system_id, row.resource_id), [])
                if row.file_id not in files:
                    files.append(row.file_id)
        return {k: sorted(v) for k, v in sorted(out.items())}
