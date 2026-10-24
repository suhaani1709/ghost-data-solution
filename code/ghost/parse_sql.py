"""SQL snapshot dumps -> units, one per row.

Each dump is executed into a fresh in-memory SQLite database; the file on
disk is only read. Tables with a record_json column carry origin_system and
collection_name; plain tables are categorized by table name. A table (or a
file whose header says so) with "replica" in its name is copy=replica, one
with "primary" is copy=primary. snapshot_scope rows are coverage metadata,
not records: every in-scope system gets one resource-less unit, so any of
its resources missing from the snapshot's rows is provably absent there.

table_coverage=True: a dump without snapshot_scope still covers the system of
each inventory table it contains (customer_profiles, customer_profiles_primary,
customer_profiles_failover_replica, ...), one resource-less unit per (system,
copy) at the header's capture time: a point-in-time dump of that table proves
a resource not in it was absent there.
"""
import json
import re
import sqlite3

from . import parse_common as pc

TOPOLOGY = re.compile(r"^-- Database topology:\s*(\S+)", re.M)
CAPTURED = re.compile(r"^-- Captured at:\s*(\S+)", re.M)
COPY_SUFFIX = re.compile(r"_(primary|failover_replica|read_replica|reporting_replica|replica(_\w+)?)$")
SKIP_TABLES = {"snapshot_scope"}
# Inventory tables -> owning system, to match snapshot_scope.origin_system.
TABLE_SYSTEMS = {
    "customer_profiles": "account_service", "customer_search_documents": "search_service",
    "customer_analytics_profiles": "analytics_platform", "support_records": "support_platform",
    "customer_exports": "export_service", "connector_subscriptions": "integration_service",
    "backup_restore_entries": "backup_service", "security_audit_records": "security_service",
}


def _copy(table, topology):
    if "replica" in table:
        return "replica"
    if "primary" in table:
        return "primary"
    if topology and "replica" in topology and topology != "primary_only":
        return "replica"
    return "unknown"


def _table_category(table):
    return pc.CATEGORY_BY_COLLECTION.get(COPY_SUFFIX.sub("", table), "")


def parse_sql(path, table_coverage=False):
    script = path.read_text(encoding="utf-8")
    top = TOPOLOGY.search(script)
    topology = top.group(1) if top else ""
    con = sqlite3.connect(":memory:")
    try:
        con.executescript(script)
        tables = [t for (t,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        scope = {}
        if "snapshot_scope" in tables:
            scope = dict(con.execute("SELECT origin_system, captured_at FROM snapshot_scope"))
        out = []
        table_of = {}
        for table in tables:
            if table in SKIP_TABLES:
                continue
            cur = con.execute(f'SELECT * FROM "{table}" ORDER BY rowid')
            cols = [d[0] for d in cur.description]
            copy = _copy(table, topology)
            rows = cur.fetchall()
            for row in rows:
                out += _row_units(table, dict(zip(cols, row)), copy)
            if TABLE_SYSTEMS.get(table) in scope:
                table_of[TABLE_SYSTEMS[table]] = (table, len(rows), copy)
        if table_coverage and not scope:
            out += _table_coverage(tables, topology, CAPTURED.search(script))
        for system in sorted(scope):
            table, n, copy = table_of.get(system, ("", 0, _copy("", topology)))
            out.append(pc.make_unit(
                system_id=system, resource_id="", category_hint=_table_category(table),
                state="", text=f"snapshot_scope {system} {scope[system]}: {table} has {n} rows",
                copy=copy, event_time=scope[system]))
        return out
    finally:
        con.close()


def _table_coverage(tables, topology, captured):
    when = captured.group(1) if captured else ""
    seen = set()
    for table in tables:
        system = TABLE_SYSTEMS.get(COPY_SUFFIX.sub("", table))
        key = (system, _copy(table, topology))
        if system and key not in seen:
            seen.add(key)
    return [pc.make_unit(system_id=s, resource_id="", category_hint="", state="",
                         text=f"table snapshot {s} ({c}) {when}", copy=c, event_time=when)
            for s, c in sorted(seen)]


def _row_units(table, row, copy):
    if "record_json" in row:
        rec = json.loads(row["record_json"])
        fields = dict(rec)
        cat = rec.get("record_type") if rec.get("record_type") in pc.CATEGORIES else \
            pc.CATEGORY_BY_COLLECTION.get(row.get("collection_name", ""), "")
        fallback = row.get("origin_system", "")
    else:
        fields = row
        cat = _table_category(table)
        fallback = ""
    rid = str(row.get("resource_id") or fields.get("resource_id") or "")
    text = table + " " + json.dumps(row, sort_keys=True, ensure_ascii=False)
    system = fields.get("system") or row.get("origin_system") or pc.system_for(rid, fallback)
    event_time = row.get("updated_at") or row.get("indexed_at") or fields.get("recorded_at") or ""
    unit = pc.make_unit(system_id=system, resource_id=rid, category_hint=cat,
                        state=pc.infer_state(fields, cat), text=text, copy=copy,
                        event_time=event_time)
    return [unit] + pc.reference_units(text, [rid], copy=copy, event_time=event_time)
