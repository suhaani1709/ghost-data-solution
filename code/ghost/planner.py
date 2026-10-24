"""Turn linked, categorized resources into (deletion_status, steps).

Input resources: (system_id, resource_id, category, observed_state, evidence_id).
No linking or evidence parsing happens here.

Category -> action comes from deletion_rules.csv. Action -> operations comes
from the operation table in problem_statement.md and the sample answers.
Where the two sources do not line up, see DISAGREEMENTS. Those points follow the
samples and are not silently merged.
"""
from collections import namedtuple

from . import loaders

# (phase, operation, state) in problem_statement.md table order; this order is
# also the within-phase sort order observed in all 32 sample answers.
OPERATIONS = (
    ("FINDING", "REPORT_REMAINING_RECORD", "PRESENT"),
    ("FINDING", "REPORT_EXPOSED_PII", "PRESENT"),
    ("FINDING", "REPORT_ACTIVE_DATA_FLOW", "ACTIVE"),
    ("FINDING", "REPORT_RESTORE_RISK", "ACTIVE"),
    ("REMEDIATION", "DISABLE_DATA_FLOW", "DISABLED"),
    ("REMEDIATION", "BLOCK_RESTORE", "BLOCKED"),
    ("REMEDIATION", "DELETE_RECORD", "ABSENT"),
    ("REMEDIATION", "REDACT_RECORD", "REDACTED"),
    ("REMEDIATION", "ANONYMIZE_RECORD", "ANONYMIZED"),
    ("VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT"),
    ("VERIFICATION", "VERIFY_RECORD_PRESENT", "PRESENT"),
    ("VERIFICATION", "VERIFY_RECORD_REDACTED", "REDACTED"),
    ("VERIFICATION", "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED"),
    ("VERIFICATION", "VERIFY_DATA_FLOW_DISABLED", "DISABLED"),
    ("VERIFICATION", "VERIFY_RESTORE_BLOCKED", "BLOCKED"),
)
PHASES = ("FINDING", "REMEDIATION", "VERIFICATION")
STATE_OF = {op: state for (_, op, state) in OPERATIONS}
PHASE_OF = {op: phase for (phase, op, _) in OPERATIONS}
OP_ORDER = {op: i for i, (_, op, _) in enumerate(OPERATIONS)}

# Treatment = (finding, remediation, verification); finding/remediation are None
# when a non-compliant state cannot be remediated (e.g. RETAIN).
Treatment = namedtuple("Treatment", "finding remediation verification")
TREATMENT_BY_ACTION = {
    "DELETE": Treatment("REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT"),
    "REDACT": Treatment("REPORT_EXPOSED_PII", "REDACT_RECORD", "VERIFY_RECORD_REDACTED"),
    "ANONYMIZE": Treatment("REPORT_EXPOSED_PII", "ANONYMIZE_RECORD", "VERIFY_RECORD_ANONYMIZED"),
    "RETAIN": Treatment(None, None, "VERIFY_RECORD_PRESENT"),
}
# Categories whose treatment the samples fix differently from action -> treatment.
SAMPLE_OVERRIDES = {
    "BACKUP_ARCHIVE": Treatment("REPORT_RESTORE_RISK", "BLOCK_RESTORE", "VERIFY_RESTORE_BLOCKED"),
    "DATA_FLOW": Treatment("REPORT_ACTIVE_DATA_FLOW", "DISABLE_DATA_FLOW", "VERIFY_DATA_FLOW_DISABLED"),
}
DISAGREEMENTS = [
    "BACKUP_ARCHIVE: rule_14 says RETAIN (which elsewhere verifies VERIFY_RECORD_PRESENT), but samples "
    "verify VERIFY_RESTORE_BLOCKED and report REPORT_RESTORE_RISK -> following the samples.",
    "DATA_FLOW: no data_category in deletion_rules.csv covers sync/import flows, but samples treat "
    "integration_service data_flow_* as DISABLE/VERIFY_DATA_FLOW_DISABLED -> pseudo-category from samples.",
    "Category is not a function of system: support_platform is SUPPORT_MESSAGE (REDACT) or "
    "SUPPORT_ATTACHMENT (DELETE); analytics_platform is ANALYTICS_PROFILE (ANONYMIZE) or "
    "MARKETING_PROFILE (DELETE). The linker must supply the category per record.",
    "No sample covers SECONDARY_IDENTIFIER, CACHE_ENTRY, PRODUCT_TELEMETRY, EMAIL_DELIVERY_LOG, "
    "LEGAL_HOLD_RECORD: their treatment comes from deletion_rules.csv alone (untested).",
    "Rule conditions (e.g. rule_05 'shared context must be retained', rule_12 'within retention period') "
    "are not evaluated here; the caller must pick the category whose condition holds.",
]


def load_treatments(rules=None):
    """{category: Treatment} from deletion_rules.csv plus the sample overrides."""
    rules = loaders.load_deletion_rules() if rules is None else rules
    out = {}
    for row in rules.itertuples(index=False):
        if row.required_action not in TREATMENT_BY_ACTION:
            raise ValueError(f"{row.rule_id}: unknown action {row.required_action!r}")
        if row.data_category in out:
            raise ValueError(f"{row.rule_id}: duplicate category {row.data_category}")
        out[row.data_category] = TREATMENT_BY_ACTION[row.required_action]
    out.update(SAMPLE_OVERRIDES)
    return out


def _step(op, system_id, resource_id, evidence_id):
    return {"step_no": 0, "phase": PHASE_OF[op], "system_id": system_id, "resource_id": resource_id,
            "operation": op, "state": STATE_OF[op], "evidence_id": evidence_id}


def _sort_key(step):
    return (PHASES.index(step["phase"]), OP_ORDER[step["operation"]], step["system_id"], step["resource_id"])


def is_zero_link(resources):
    """True when a deletion request has no linked, categorized resource (zero-link rule)."""
    return not list(resources)


def build_steps(resources, treatments=None):
    """resources: iterable of (system_id, resource_id, category, observed_state, evidence_id).

    Returns (status, steps) with status COMPLETE or INCOMPLETE.
    A resource is compliant when observed_state equals its required final state.
    Zero-link rule (NOTES.md): no resources -> ("COMPLETE", []); nothing remaining is
    evidenced, and no verification step is invented without evidence.
    """
    resources = list(resources)
    if is_zero_link(resources):
        return "COMPLETE", []
    treatments = load_treatments() if treatments is None else treatments
    seen, plan = set(), []
    for system_id, resource_id, category, observed, evidence_id in resources:
        if (system_id, resource_id) in seen:
            raise ValueError(f"duplicate resource {system_id}/{resource_id}")
        seen.add((system_id, resource_id))
        if category not in treatments:
            raise ValueError(f"{system_id}/{resource_id}: unknown category {category!r}")
        t = treatments[category]
        compliant = observed == STATE_OF[t.verification]
        if not compliant and (t.finding is None or observed != STATE_OF[t.finding]):
            raise ValueError(f"{system_id}/{resource_id}: unsupported state {observed!r} for {category}")
        plan.append((system_id, resource_id, t, compliant, evidence_id))

    if all(compliant for *_, compliant, _ in plan):
        steps = [_step(t.verification, s, r, ev) for s, r, t, _, ev in plan]
        status = "COMPLETE"
    else:
        steps = []
        for s, r, t, compliant, ev in plan:
            if not compliant:
                steps.append(_step(t.finding, s, r, ev))
                steps.append(_step(t.remediation, s, r, ""))
            steps.append(_step(t.verification, s, r, ""))
        status = "INCOMPLETE"

    steps.sort(key=_sort_key)
    for i, step in enumerate(steps, 1):
        step["step_no"] = i
    return status, steps
