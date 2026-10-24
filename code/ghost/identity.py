"""Subject identity: current + historical identifiers per user, and exact
resolution of a request email to a user.

Matching is exact only (emails lowercased and stripped). There is deliberately
no fuzzy matching or edit distance: the evidence contains look-alike decoy
emails that must not resolve.
"""
import hashlib
from dataclasses import dataclass
from typing import NamedTuple, Optional

from . import loaders


def normalize_email(email):
    return email.strip().lower()


def email_sha256(email):
    return hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IdentitySet:
    user_id: str
    name: str
    email: str            # current, normalized
    phone: str            # current, verbatim
    email_hash: str       # current, as given in the snapshot
    emails: frozenset     # current + every audit-log old/new email, normalized
    historical_emails: frozenset  # emails minus the current one
    phones: frozenset     # current + every audit-log old/new phone
    email_hashes: frozenset  # snapshot/audit hashes + sha256 of every email

    def identifiers(self):
        """Every token that can link evidence to this user."""
        tokens = {self.user_id, self.name} | self.emails | self.phones | self.email_hashes
        return frozenset(t for t in tokens if t)


class Resolution(NamedTuple):
    user_id: Optional[str]  # None when unresolved or ambiguous
    match: str              # "current" | "historical" | "none" | "ambiguous"
    candidates: tuple       # every (user_id, kind) the email matched


def build_identity_sets(identities, audit_log):
    """Return {user_id: IdentitySet} from the snapshot and the audit log."""
    history = {}
    for row in audit_log.itertuples(index=False):
        field = row.field_name
        bucket = history.setdefault(row.user_id, {"email": set(), "phone": set(), "email_hash": set()})
        if field not in bucket:
            raise ValueError(f"{row.audit_id}: unexpected field_name {field!r}")
        for value in (row.old_value, row.new_value):
            if value:
                bucket[field].add(normalize_email(value) if field == "email" else value.strip())

    sets = {}
    for row in identities.itertuples(index=False):
        hist = history.get(row.user_id, {"email": set(), "phone": set(), "email_hash": set()})
        current = normalize_email(row.email)
        emails = {current} | hist["email"]
        hashes = {row.email_hash} | hist["email_hash"] | {email_sha256(e) for e in emails}
        sets[row.user_id] = IdentitySet(
            user_id=row.user_id,
            name=row.name,
            email=current,
            phone=row.phone,
            email_hash=row.email_hash,
            emails=frozenset(e for e in emails if e),
            historical_emails=frozenset(e for e in emails if e and e != current),
            phones=frozenset(p for p in {row.phone} | hist["phone"] if p),
            email_hashes=frozenset(h for h in hashes if h),
        )
    unknown = set(history) - set(sets)
    if unknown:
        raise ValueError(f"audit log references users missing from the snapshot: {sorted(unknown)}")
    return sets


class IdentityIndex:
    def __init__(self, identity_sets):
        self.sets = identity_sets
        self._by_email = {}
        for ident in identity_sets.values():
            for email in ident.emails:
                kind = "current" if email == ident.email else "historical"
                self._by_email.setdefault(email, set()).add((ident.user_id, kind))

    @classmethod
    def from_dataset(cls, dataset_dir=None):
        return cls(build_identity_sets(loaders.load_user_identities(dataset_dir),
                                       loaders.load_user_audit_log(dataset_dir)))

    def resolve_email(self, email):
        candidates = tuple(sorted(self._by_email.get(normalize_email(email), ())))
        users = {uid for uid, _ in candidates}
        if not users:
            return Resolution(None, "none", candidates)
        if len(users) > 1:
            return Resolution(None, "ambiguous", candidates)
        (user_id, kind), = candidates
        return Resolution(user_id, kind, candidates)

    def resolve_request(self, case):
        """case: a request row (mapping or namedtuple with an `email` field)."""
        email = case["email"] if isinstance(case, dict) or hasattr(case, "keys") else case.email
        return self.resolve_email(email)


_default_index = None


def resolve_request(case, index=None):
    """Resolve a request to a user via its email (current or historical).

    Returns a Resolution; `.user_id` is the user and `.match` says whether the
    email is the user's current or a historical one.
    """
    global _default_index
    if index is None:
        if _default_index is None:
            _default_index = IdentityIndex.from_dataset()
        index = _default_index
    return index.resolve_request(case)
