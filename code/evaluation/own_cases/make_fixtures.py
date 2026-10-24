"""Writes code/evaluation/own_cases/*/ (fictional data only). The expected answers and CASE.md
derivations were written by hand from the rules before the pipeline was run on them.

Run:  python3 code/evaluation/own_cases/make_fixtures.py .   (from the repo root)
"""
import csv, hashlib, json, shutil, sys
from pathlib import Path

ROOT = Path(sys.argv[1])
OWN = ROOT / "code/evaluation/own_cases"
RULES = ROOT / "dataset/deletion_rules.csv"
H = lambda e: hashlib.sha256(e.lower().encode()).hexdigest()

def wcsv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(header); w.writerows(rows)

def step(no, phase, sys_, rid, op, state, ev):
    return {"step_no": no, "phase": phase, "system_id": sys_, "resource_id": rid,
            "operation": op, "state": state, "evidence_id": ev}

def case(name, *, request, identities, audit=(), activity=(), files, expected, derivation):
    d = OWN / name / "dataset"
    if (OWN / name).exists():
        shutil.rmtree(OWN / name)
    (d / "evidence").mkdir(parents=True)
    wcsv(d / "deletion_requests.csv",
         ["case_id", "email", "requested_at", "reported_status", "reported_at", "audit_at", "request_text"], [request])
    wcsv(d / "user_identities.csv", ["user_id", "name", "email", "phone", "email_hash", "updated_at"],
         [(u, n, e, p, H(e), t) for (u, n, e, p, t) in identities])
    wcsv(d / "user_audit_log.csv", ["audit_id", "user_id", "event_time", "field_name", "old_value", "new_value"], audit)
    wcsv(d / "system_activity.csv", ["activity_id", "event_time", "event_type", "source_system", "target_system",
                                     "resource_id", "reported_result", "details"], activity)
    shutil.copy(RULES, d / "deletion_rules.csv")
    man = []
    for fid, rel, origin, cap, body in files:
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body if isinstance(body, str) else json.dumps(body, indent=2) + "\n", encoding="utf-8")
        man.append((fid, rel, origin, cap))
    wcsv(d / "evidence_files.csv", ["file_id", "file_path", "origin", "captured_at"], man)
    status, steps = expected
    wcsv(OWN / name / "expected_output.csv", ["case_id", "deletion_status", "steps_json"],
         [(request[0], status, json.dumps(steps, sort_keys=True, separators=(",", ":")))])
    (OWN / name / "CASE.md").write_text(derivation.strip() + "\n", encoding="utf-8")

ADA = ("user_9001", "Ada Quill", "ada.quill@example.com", "+1 555 0101", "2026-01-10T09:00:00Z")
BEN = ("user_9002", "Ben Okafor-Lind", "ben.okafor@example.com", "+1 555 0102", "2026-01-10T09:00:00Z")
DELETE_TEXT = "Please permanently delete the account associated with this email address."

def profile(rid, u):
    return {"resource_id": rid, "user_id": u[0], "full_name": u[1], "email": u[2], "phone": u[3],
            "account_status": "ACTIVE", "updated_at": "2026-04-30T10:00:00Z"}

# (a) explicit refusal of deletion -------------------------------------------------
case("a_do_not_delete",
     request=("own_a", ADA[2], "2026-05-02T08:00:00Z", "NOT_STARTED", "2026-05-02T09:00:00Z",
              "2026-05-20T00:00:00Z", "Please do not delete my account. I still use it every week."),
     identities=[ADA, BEN],
     files=[("evidence_a1", "evidence/records/customer_data_snapshot_bundle_20260501.json",
             "records_assurance_snapshot_bundle", "2026-05-01T12:00:00Z",
             {"exported_at": "2026-05-01T12:00:00Z", "source": "records_assurance_service", "snapshots": [
                 {"captured_at": "2026-05-01T08:00:00Z", "data_store": "account_service",
                  "collection": "customer_profiles", "records": [profile("account_9001", ADA)]}]})],
     expected=("NOT_APPLICABLE", []),
     derivation="""
# Own case (a): "please do not delete my account"

**Input.** One request from `ada.quill@example.com` (user_9001, current email):
"Please do not delete my account. I still use it every week." Evidence: one snapshot
bundle (evidence_a1, 2026-05-01) that still holds `account_9001` with the user's email.

**Hand derivation (written before running the pipeline).**
AGENTS.md §6.5: first decide whether `request_text` authorizes deletion. The text
explicitly refuses deletion, so nothing is authorized. problem_statement.md:
NOT_APPLICABLE rows use `[]`. The present profile row is irrelevant: no deletion
was requested, so it is not a violation.

**Expected:** `own_a,NOT_APPLICABLE,[]`
""")

# (b) look-alike decoys must not link -----------------------------------------------
decoy_email = "ada.quill@exarnple.com"     # "rn" for "m"
decoy_hash_email = "ada.quil@example.com"  # one "l" dropped
case("b_lookalike_decoy",
     request=("own_b", ADA[2], "2026-05-03T08:00:00Z", "COMPLETE", "2026-05-25T09:00:00Z",
              "2026-06-15T00:00:00Z", DELETE_TEXT),
     identities=[ADA, BEN],
     files=[
         ("evidence_b1", "evidence/records/customer_data_snapshot_bundle_20260501.json",
          "records_assurance_snapshot_bundle", "2026-05-01T12:00:00Z",
          {"exported_at": "2026-05-01T12:00:00Z", "source": "records_assurance_service", "snapshots": [
              {"captured_at": "2026-05-01T08:00:00Z", "data_store": "account_service",
               "collection": "customer_profiles",
               "records": [profile("account_9001", ADA), profile("account_9002", BEN)]}]}),
         ("evidence_b2", "evidence/records/customer_data_snapshot_bundle_20260601.json",
          "records_assurance_snapshot_bundle", "2026-06-01T12:00:00Z",
          {"exported_at": "2026-06-01T12:00:00Z", "source": "records_assurance_service", "snapshots": [
              {"captured_at": "2026-06-01T08:00:00Z", "data_store": "account_service",
               "collection": "customer_profiles", "records": []},
              {"captured_at": "2026-06-01T08:00:00Z", "data_store": "search_service",
               "collection": "customer_search_documents",
               "records": [{"resource_id": "search_9002", "index_name": "customer_directory_v3",
                            "document": {"display_name": "Ada Quill", "email": decoy_email,
                                         "customer_reference": None}}]},
              {"captured_at": "2026-06-01T08:00:00Z", "data_store": "analytics_platform",
               "collection": "customer_analytics_reports",
               "records": [{"resource_id": "analytics_9003", "user_id": None, "email": None,
                            "phone": None, "email_hash": H(decoy_hash_email),
                            "reporting_window": "last_90_days"}]}]})],
     expected=("COMPLETE", [step(1, "VERIFICATION", "account_service", "account_9001",
                                 "VERIFY_RECORD_ABSENT", "ABSENT", "evidence_b2")]),
     derivation=f"""
# Own case (b): look-alike decoy identifiers must not link

**Input.** A deletion request from `ada.quill@example.com` (user_9001), audit_at 2026-06-15.
- evidence_b1 (2026-05-01): `account_9001` holds the user's email, so it is the user's profile.
- evidence_b2 (2026-06-01): the `account_service` / `customer_profiles` snapshot is empty.
  The same bundle holds two decoys: `search_9002` with display name "Ada Quill" and the
  look-alike email `{decoy_email}` ("rn" in place of "m"), and `analytics_9003` whose
  `email_hash` is SHA-256 of the look-alike `{decoy_hash_email}`. Neither is a token of user_9001.

**Hand derivation (written before running the pipeline).**
AGENTS.md §6.6: match evidence through exact identifiers. A look-alike email or the hash of
one is not the user's identifier, and a shared display name alone is not a grounded link.
The only relevant resource is `account_9001` (USER_PROFILE, rule_01 DELETE). The latest
evidence on or before audit_at is evidence_b2, a covering snapshot of account_service
without the row, so the record is ABSENT. That is compliant, and the case is COMPLETE
with one verification step citing evidence_b2.

**Expected:** COMPLETE,
`[{{1, VERIFICATION, account_service, account_9001, VERIFY_RECORD_ABSENT, ABSENT, evidence_b2}}]`.
A row for search_9002 or analytics_9003 would be a decoy false positive.
""")

# (c) primary deleted, failover replica still holds the row --------------------------
CORA = ("user_9101", "Cora Vance", "cora.vance@example.com", "+1 555 0111", "2026-01-12T09:00:00Z")
def sql_row(table, u, rid):
    return (f"INSERT INTO \"{table}\" VALUES('{rid}','{u[0]}','{u[1]}','{u[2]}','{u[3]}',"
            f"'ACTIVE','2026-06-20T22:45:00Z');\n")
ddl = lambda t: (f"CREATE TABLE {t} (\n                resource_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,\n"
                 "                full_name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL,\n"
                 "                account_status TEXT NOT NULL, updated_at TEXT NOT NULL\n            );\n")
sql = ("-- Ghost Data Still Exists: point-in-time database snapshot\n-- Dialect: SQLite-compatible SQL\n"
       "-- Captured at: 2026-06-20T23:00:00Z\n-- Database topology: failover_replica\n"
       "-- Compare the primary and any replica tables for replication drift.\n\nBEGIN TRANSACTION;\n"
       + ddl("customer_profiles_failover_replica")
       + sql_row("customer_profiles_failover_replica", CORA, "account_9101")
       + sql_row("customer_profiles_failover_replica", BEN, "account_9002")
       + ddl("customer_profiles_primary")
       + sql_row("customer_profiles_primary", BEN, "account_9002") + "COMMIT;\n")
case("c_replica_holds_row",
     request=("own_c", CORA[2], "2026-06-10T08:00:00Z", "COMPLETE", "2026-06-19T09:00:00Z",
              "2026-07-10T00:00:00Z",
              "I would like to submit a request to delete this account and its personal data."),
     identities=[CORA, BEN],
     activity=[("activity_c1", "2026-06-18T05:10:32Z", "DELETE_RECORD", "deletion_worker", "account_service",
                "account_9101", "SUCCESS", "Deletion worker submitted primary profile account_9101 to account_service.")],
     files=[("evidence_c1", "evidence/databases/customer_accounts_failover_replica_20260620.sql",
             "customer_accounts_failover_replica_capture", "2026-06-20T23:00:00Z", sql)],
     expected=("INCOMPLETE", [
         step(1, "FINDING", "account_service", "account_9101", "REPORT_REMAINING_RECORD", "PRESENT", "evidence_c1"),
         step(2, "REMEDIATION", "account_service", "account_9101", "DELETE_RECORD", "ABSENT", ""),
         step(3, "VERIFICATION", "account_service", "account_9101", "VERIFY_RECORD_ABSENT", "ABSENT", "")]),
     derivation="""
# Own case (c): primary deleted, failover replica still holds the row

**Input.** A deletion request from `cora.vance@example.com` (user_9101). reported_status is
COMPLETE, and activity_c1 claims DELETE_RECORD SUCCESS on `account_9101` (2026-06-18).
evidence_c1 (SQL, 2026-06-20) has `customer_profiles_primary` without account_9101, but
`customer_profiles_failover_replica` still holds account_9101 with the user's name, email and phone.

**Hand derivation (written before running the pipeline).**
Reported statuses and activity results are claims (§6.6). README: SQL captures can hold
replicas "so replication drift can be investigated directly". A copy of the profile still
exists in the failover replica, so the USER_PROFILE (rule_01 DELETE) record is PRESENT, cited
to evidence_c1. With no data flow or backup in evidence, the plan is: finding, delete, and
verify absent. Remediation and future verification use `""`.

**Expected:** INCOMPLETE,
1 FINDING REPORT_REMAINING_RECORD account_service/account_9101 PRESENT evidence_c1;
2 REMEDIATION DELETE_RECORD ... ABSENT "";
3 VERIFICATION VERIFY_RECORD_ABSENT ... ABSENT "".
""")

# (d) old email, resource only under that email's SHA-256 ----------------------------
OLD = "dev.m.old@example.com"
DEV = ("user_9201", "Dev Marlow", "dev.marlow@example.org", "+1 555 0121", "2026-02-01T10:00:00Z")
log = (
    '2026-07-01T09:50:02Z requestId=collector-1 level=DEBUG function=log_router message="instance=\\"collector-1\\" event=\\"export_started\\" sources=\\"platform_services\\" expected_source_events=\\"3\\""\n'
    '2026-07-01T09:53:26Z requestId=tr-9301001 level=INFO function=search_service message="instance=\\"search-2\\" pod=\\"search-12e2\\" region=\\"us-east-2\\" resource_id=\\"search_9301\\" event=\\"index_query_completed\\" index=\\"customer_directory_v3\\" result=\\"hit\\" shard=\\"7\\" took_ms=\\"10\\" correlation_key=\\"' + H(OLD) + '\\""\n'
    '2026-07-01T09:53:34Z requestId=tr-9301002 level=INFO function=account_service message="instance=\\"account-5\\" pod=\\"account-37ba\\" region=\\"us-east-2\\" resource_id=\\"account_9302\\" event=\\"profile_lookup_completed\\" rows=\\"0\\" http_status=\\"404\\" duration_ms=\\"57\\""\n')
case("d_old_email_hash_only",
     request=("own_d", OLD, "2026-06-01T08:00:00Z", "COMPLETE", "2026-06-20T09:00:00Z", "2026-08-01T00:00:00Z",
              "Please erase the account linked to this email address."),
     identities=[DEV, BEN],
     audit=[("audit_d1", "user_9201", "2026-02-01T10:00:00Z", "email", OLD, DEV[2])],
     files=[("evidence_d1", "evidence/logs/cloud_runtime_export_us_west_20260701.log",
             "central_observability_export", "2026-07-01T10:00:00Z", log)],
     expected=("INCOMPLETE", [
         step(1, "FINDING", "search_service", "search_9301", "REPORT_REMAINING_RECORD", "PRESENT", "evidence_d1"),
         step(2, "REMEDIATION", "search_service", "search_9301", "DELETE_RECORD", "ABSENT", ""),
         step(3, "VERIFICATION", "search_service", "search_9301", "VERIFY_RECORD_ABSENT", "ABSENT", "")]),
     derivation=f"""
# Own case (d): old email whose resource appears only under its SHA-256

**Input.** A deletion request from `{OLD}`. That email is not in `user_identities.csv`.
audit_d1 (2026-02-01) shows user_9201 changed email from it to `{DEV[2]}`. evidence_d1
(log, 2026-07-01) has an `index_query_completed` hit on `search_9301` whose `correlation_key`
is SHA-256(`{OLD}`) = `{H(OLD)}`. The plain old email appears nowhere in the evidence.
`account_9302` returns 404 in the same log, but nothing ties it to the user.

**Hand derivation (written before running the pipeline).**
§6.5: resolve current and historical identifiers; the request email may be historical, so
it resolves to user_9201. §6.6: match through hashes too. The SHA-256 of the historical
email is a user token, so search_9301 is the user's search entry (SEARCH_INDEX_ENTRY,
rule_03 DELETE). An index hit on 2026-07-01, before audit_at, means the entry is PRESENT.
account_9302 is not linked to any user token, so it is not reported.

**Expected:** INCOMPLETE,
1 FINDING REPORT_REMAINING_RECORD search_service/search_9301 PRESENT evidence_d1;
2 REMEDIATION DELETE_RECORD ... ABSENT "";
3 VERIFICATION VERIFY_RECORD_ABSENT ... ABSENT "".
""")
# (e) late-exported log: events before audit_at, file captured after it -------------------
EVE = ("user_9301", "Eve Tran", "eve.tran@example.com", "+1 555 0131", "2026-03-01T10:00:00Z")
def jline(ts, service, trace, event, **kv):
    return ts + " " + json.dumps({"severity": "INFO", "logger": service, "service": service,
                                  "trace_id": trace, "event": event, **kv}, separators=(",", ":")) + "\n"
late_log = (jline("2026-07-10T08:50:00Z", "security_service", "tr-9402", "audit_record_query_started",
                  subject_ref=EVE[0], attempt="1")
            + jline("2026-07-10T08:50:05Z", "security_service", "tr-9402", "audit_record_read_completed",
                    resource_id="audit_record_9402", integrity_check="passed", rows="1")
            + jline("2026-07-10T09:30:00Z", "account_service", "tr-9403", "profile_lookup_started",
                    lookup_key=EVE[2], attempt="1")
            + jline("2026-07-10T09:30:02Z", "account_service", "tr-9403", "profile_lookup_completed",
                    resource_id="account_9403", rows="0", http_status="404"))
def search_bundle(cap, records):
    return {"exported_at": cap, "source": "records_assurance_service", "snapshots": [
        {"captured_at": cap, "data_store": "search_service", "collection": "customer_search_documents",
         "records": records}]}
def search_doc(rid, u):
    return {"resource_id": rid, "index_name": "customer_directory_v3",
            "document": {"display_name": u[1], "email": u[2], "customer_reference": None}}
LATE_DERIVATION = """
**Late-export rule (AGENTS.md §6.2, §6.6, problem_statement.md Rules).** Use only information
available at or before audit_at, and never cite a file captured after it. The log file was
exported after audit_at, but its trace events are timestamped before audit_at, so the facts
existed at audit time. They can establish that the record belongs to the user, but the file
cannot be cited. A retained SECURITY_AUDIT_LOG record (rule RETAIN) only adds a
VERIFY_RECORD_PRESENT step. In an INCOMPLETE case, that future check carries evidence_id "",
so it needs no citation. The trace dated after audit_at (account lookup at 09:30) is ignored.
"""
case("e_late_export_incomplete",
     request=("own_e", EVE[2], "2026-07-01T08:00:00Z", "COMPLETE", "2026-07-03T09:00:00Z",
              "2026-07-10T09:00:00Z", DELETE_TEXT),
     identities=[EVE, BEN],
     files=[("evidence_e1", "evidence/records/customer_data_snapshot_bundle_20260708.json",
             "records_assurance_snapshot_bundle", "2026-07-08T12:00:00Z",
             search_bundle("2026-07-08T12:00:00Z", [search_doc("search_9401", EVE)])),
            ("evidence_e2", "evidence/logs/structured_service_events_eu_west_20260712.log",
             "central_observability_export", "2026-07-12T11:00:00Z", late_log)],
     expected=("INCOMPLETE", [
         step(1, "FINDING", "search_service", "search_9401", "REPORT_REMAINING_RECORD", "PRESENT", "evidence_e1"),
         step(2, "REMEDIATION", "search_service", "search_9401", "DELETE_RECORD", "ABSENT", ""),
         step(3, "VERIFICATION", "search_service", "search_9401", "VERIFY_RECORD_ABSENT", "ABSENT", ""),
         step(4, "VERIFICATION", "security_service", "audit_record_9402", "VERIFY_RECORD_PRESENT", "PRESENT", "")]),
     derivation="""
# Own case (e): late-exported log, INCOMPLETE case

**Input.** A deletion request from `eve.tran@example.com` (user_9301), audit_at 2026-07-10T09:00.
evidence_e1 (captured 2026-07-08) still holds `search_9401` with the user's email.
evidence_e2 is a log captured 2026-07-12, after audit_at. Trace tr-9402 (08:50, before
audit_at) queries `subject_ref=user_9301` and reads `audit_record_9402` (rows=1). Trace tr-9403
(09:30, after audit_at) looks up the user's email, and `account_9403` returns 404.
""" + LATE_DERIVATION + """
**Hand derivation (written before running the pipeline).** search_9401 is a SEARCH_INDEX_ENTRY
(rule_03 DELETE), PRESENT and cited to evidence_e1, so the case is INCOMPLETE. audit_record_9402
is the user's retained security record, so it gets VERIFY_RECORD_PRESENT with "". account_9403
is known only from an event after audit_at and is not reported.

**Expected:** INCOMPLETE: REPORT_REMAINING_RECORD search_9401 (evidence_e1); DELETE_RECORD
search_9401; VERIFY_RECORD_ABSENT search_9401; VERIFY_RECORD_PRESENT audit_record_9402 ("").
""")

# (f) the same late log in a case that is otherwise COMPLETE ------------------------------
case("f_late_export_complete",
     request=("own_f", EVE[2], "2026-07-01T08:00:00Z", "COMPLETE", "2026-07-03T09:00:00Z",
              "2026-07-10T09:00:00Z", DELETE_TEXT),
     identities=[EVE, BEN],
     files=[("evidence_f1", "evidence/records/customer_data_snapshot_bundle_20260620.json",
             "records_assurance_snapshot_bundle", "2026-06-20T12:00:00Z",
             search_bundle("2026-06-20T12:00:00Z", [search_doc("search_9401", EVE)])),
            ("evidence_f2", "evidence/records/customer_data_snapshot_bundle_20260708.json",
             "records_assurance_snapshot_bundle", "2026-07-08T12:00:00Z",
             search_bundle("2026-07-08T12:00:00Z", [])),
            ("evidence_f3", "evidence/logs/structured_service_events_eu_west_20260712.log",
             "central_observability_export", "2026-07-12T11:00:00Z", late_log)],
     expected=("COMPLETE", [
         step(1, "VERIFICATION", "search_service", "search_9401", "VERIFY_RECORD_ABSENT", "ABSENT", "evidence_f2")]),
     derivation="""
# Own case (f): late-exported log, COMPLETE case

**Input.** The same user and the same late log as case (e) (here evidence_f3, captured after
audit_at). evidence_f1 (2026-06-20) holds `search_9401` with the user's email. evidence_f2
(2026-07-08) is a covering search_service snapshot without it.
""" + LATE_DERIVATION + """
**Hand derivation (written before running the pipeline).** search_9401 is ABSENT at audit_at,
cited to evidence_f2, so it is compliant and the case is COMPLETE. In a COMPLETE case every
verification step must cite evidence captured at or before audit_at. audit_record_9402 is
evidenced only by evidence_f3, captured after audit_at, so no valid citation exists. It is
omitted rather than cited to a late file or given an invented citation. It cannot change the
status either way, because it is retained and compliant.

**Expected:** COMPLETE: VERIFY_RECORD_ABSENT search_9401 (evidence_f2).
""")

# (g) refusal of deletion in an unseen language ---------------------------------------------
case("g_spanish_refusal",
     request=("own_g", ADA[2], "2026-05-02T08:00:00Z", "NOT_STARTED", "2026-05-02T09:00:00Z",
              "2026-05-20T00:00:00Z", "Por favor, no eliminen mi cuenta. Todavía la uso para mis pedidos."),
     identities=[ADA, BEN],
     files=[("evidence_g1", "evidence/records/customer_data_snapshot_bundle_20260501.json",
             "records_assurance_snapshot_bundle", "2026-05-01T12:00:00Z",
             {"exported_at": "2026-05-01T12:00:00Z", "source": "records_assurance_service", "snapshots": [
                 {"captured_at": "2026-05-01T08:00:00Z", "data_store": "account_service",
                  "collection": "customer_profiles", "records": [profile("account_9001", ADA)]}]})],
     expected=("NOT_APPLICABLE", []),
     derivation="""
# Own case (g): refusal of deletion in Spanish (unseen wording)

**Input.** "Por favor, no eliminen mi cuenta. Todavía la uso para mis pedidos." ("Please do not
delete my account. I still use it for my orders.") A live profile row exists in evidence_g1.

**Hand derivation (written before running the pipeline).** §6.5: the text explicitly refuses
deletion, so nothing is authorized. The answer is NOT_APPLICABLE with `[]`. The text is in none
of the sentence tables, so this tests the cue fallback, which must fail closed.

**Expected:** `own_g,NOT_APPLICABLE,[]`
""")
print("fixtures written to", OWN)
