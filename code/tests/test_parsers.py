"""Acceptance tests for the evidence parsers and the flat observation table.

Run:  python3 code/tests/test_parsers.py      (summary + tests)
      python3 -m unittest discover -s code/tests -v   (tests only)

The unit tests use made-up snippets in every log syntax; the acceptance tests
run over the real evidence files (all except the PNG screenshots).
"""
import hashlib
import json
import re
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghost import loaders, observations, parse_common, parse_logs, parse_records, parse_sql  # noqa: E402

EVIDENCE_DIR = loaders.DATASET_DIR / "evidence"
OBS_FIELDS = ["file_id", "captured_at", "file_kind", "system_id", "resource_id",
              "category_hint", "state", "identifiers", "copy", "event_time", "raw_snippet"]

_TABLE = None


def table():
    global _TABLE
    if _TABLE is None:
        _TABLE = observations.build_observations()
    return _TABLE


def text_files():
    manifest = loaders.load_evidence_files()
    return manifest[~manifest.file_path.str.lower().str.endswith(".png")]


def raw_text(path):
    if path.suffix.lower() == ".pdf":
        return "\n".join(parse_common.pdf_pages(path))
    return path.read_text(encoding="utf-8")


# The same two events written in each of the six log syntaxes.
STARTED = {
    "bracket": '2026-01-01T00:00:01Z [DEBUG] [account_service] [tr-1] profile_lookup_started: '
               'instance="a-1" lookup_key="Jane.Doe@Example.com" attempt="1"',
    "pipe": '2026-01-01T00:00:01Z | DEBUG | account_service | tr-1 | profile_lookup_started | '
            'instance="a-1" lookup_key="Jane.Doe@Example.com" attempt="1"',
    "logfmt": '2026-01-01T00:00:01Z level=DEBUG service=account_service trace_id=tr-1 '
              'event=profile_lookup_started lookup_key="Jane.Doe@Example.com" attempt=1',
    "json": '2026-01-01T00:00:01Z {"severity":"DEBUG","service":"account_service","trace_id":"tr-1",'
            '"event":"profile_lookup_started","lookup_key":"Jane.Doe@Example.com","attempt":"1"}',
    "syslog": '2026-01-01T00:00:01Z <15>1 node-1 account_service tr-1 - - level=DEBUG '
              'event="profile_lookup_started" lookup_key="Jane.Doe@Example.com" attempt="1"',
    "cloud": '2026-01-01T00:00:01Z requestId=tr-1 level=DEBUG function=account_service '
             'message="event=\\"profile_lookup_started\\" lookup_key=\\"Jane.Doe@Example.com\\" attempt=\\"1\\""',
}
COMPLETED = {
    "bracket": '2026-01-01T00:00:02Z [INFO] [account_service] [tr-1] profile_lookup_completed: '
               'instance="a-1" resource_id="account_42" rows="0" http_status="404"',
    "pipe": '2026-01-01T00:00:02Z | INFO | account_service | tr-1 | profile_lookup_completed | '
            'instance="a-1" resource_id="account_42" rows="0" http_status="404"',
    "logfmt": '2026-01-01T00:00:02Z level=INFO service=account_service trace_id=tr-1 '
              'resource_id=account_42 event=profile_lookup_completed rows=0 http_status=404',
    "json": '2026-01-01T00:00:02Z {"severity":"INFO","service":"account_service","trace_id":"tr-1",'
            '"resource_id":"account_42","event":"profile_lookup_completed","rows":"0","http_status":"404"}',
    "syslog": '2026-01-01T00:00:02Z <15>1 node-1 account_service tr-1 - - level=INFO '
              'resource_id="account_42" event="profile_lookup_completed" rows="0" http_status="404"',
    "cloud": '2026-01-01T00:00:02Z requestId=tr-1 level=INFO function=account_service '
             'message="resource_id=\\"account_42\\" event=\\"profile_lookup_completed\\" '
             'rows=\\"0\\" http_status=\\"404\\""',
}


class LogGrammarTest(unittest.TestCase):
    def test_every_syntax_parses_to_one_event_grammar(self):
        for syntax in STARTED:
            with self.subTest(syntax=syntax):
                ev = parse_logs.parse_line(STARTED[syntax])
                self.assertEqual(ev["syntax"], syntax)
                self.assertEqual(ev["ts"], "2026-01-01T00:00:01Z")
                self.assertEqual(ev["service"], "account_service")
                self.assertEqual(ev["trace_id"], "tr-1")
                self.assertEqual(ev["event"], "profile_lookup_started")
                self.assertEqual(ev["fields"]["lookup_key"], "Jane.Doe@Example.com")

    def test_started_and_completed_join_on_trace_id(self):
        for syntax in STARTED:
            with self.subTest(syntax=syntax):
                units = parse_logs.parse_lines([STARTED[syntax], COMPLETED[syntax]])
                self.assertEqual(len(units), 1)
                u = units[0]
                self.assertEqual(u["resource_id"], "account_42")
                self.assertEqual(u["system_id"], "account_service")
                self.assertEqual(u["category_hint"], "USER_PROFILE")
                self.assertEqual(u["state"], "ABSENT")
                self.assertEqual(u["identifiers"]["emails"], ["jane.doe@example.com"])
                self.assertEqual(u["event_time"], "2026-01-01T00:00:02Z")

    def test_replica_pool_marks_copy(self):
        lines = [STARTED["logfmt"],
                 '2026-01-01T00:00:01Z level=DEBUG service=account_service trace_id=tr-1 '
                 'event=connection_acquired pool=account_service_replica',
                 COMPLETED["logfmt"]]
        self.assertEqual(parse_logs.parse_lines(lines)[0]["copy"], "replica")

    def test_category_comes_from_event_semantics_not_system(self):
        line = ('2026-01-01T00:00:00Z level=INFO service=analytics_platform trace_id=tr-9 '
                'event=contact_lookup_completed resource_id=analytics_7 rows=1 email_opt_in=true '
                'correlation_key="x@example.com"')
        u = parse_logs.parse_lines([line])[0]
        self.assertEqual(u["system_id"], "analytics_platform")
        self.assertEqual(u["category_hint"], "MARKETING_PROFILE")
        self.assertEqual(u["state"], "PRESENT")

    def test_record_lookup_uses_record_type_and_result(self):
        line = ('2026-01-01T00:00:00Z INFO service=downstream event=record_lookup seq=1 '
                'system="account_service" resource_id="account_9" record_type="USER_PROFILE" '
                'result="NOT_FOUND" subject_reference="y@example.com"')
        u = parse_logs.parse_lines([line])[0]
        self.assertEqual((u["category_hint"], u["state"]), ("USER_PROFILE", "ABSENT"))


class RecordParserTest(unittest.TestCase):
    def test_service_export_and_snapshot_shapes(self):
        doc = {"exported_at": "2026-01-01T00:00:00Z", "service_exports": {
            "integration_service": {"connectors": [{
                "resource_id": "data_flow_1", "enabled": True, "customer_email": "z@example.com",
                "customer_reference": None, "observed_at": "2026-01-01T00:00:00Z"}]}},
            "snapshots": [{"captured_at": "2026-01-02T00:00:00Z", "data_store": "analytics_platform",
                           "collection": "customer_analytics_reports",
                           "records": [{"resource_id": "analytics_1", "user_id": None, "email": None,
                                        "phone": None, "email_hash": None}]}]}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.json"
            p.write_text(json.dumps(doc), encoding="utf-8")
            units = {u["resource_id"]: u for u in parse_records.parse_json(p)}
        self.assertEqual((units["data_flow_1"]["category_hint"], units["data_flow_1"]["state"]),
                         ("DATA_FLOW", "ACTIVE"))
        self.assertEqual((units["analytics_1"]["category_hint"], units["analytics_1"]["state"]),
                         ("ANALYTICS_PROFILE", "ANONYMIZED"))


class SqlParserTest(unittest.TestCase):
    def test_replica_table_and_record_json(self):
        sql = ("CREATE TABLE customer_data_replica_eu_west (resource_id TEXT, origin_system TEXT, "
               "collection_name TEXT, record_json TEXT, updated_at TEXT);\n"
               "INSERT INTO customer_data_replica_eu_west VALUES ('tombstone_1','identity_service',"
               "'deleted_customer_references','{\"resource_id\":\"tombstone_1\",\"subject_reference\":"
               "\"user_5\",\"name\":null,\"email\":null,\"phone\":null,\"email_hash\":null}',"
               "'2026-01-01T00:00:00Z');\n")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.sql"
            p.write_text(sql, encoding="utf-8")
            u = parse_sql.parse_sql(p)[0]
        self.assertEqual(u["copy"], "replica")
        self.assertEqual(u["system_id"], "identity_service")
        self.assertEqual((u["category_hint"], u["state"]), ("ACCOUNT_TOMBSTONE", "REDACTED"))
        self.assertEqual(u["identifiers"]["user_ids"], ["user_5"])


class EvidenceAcceptanceTest(unittest.TestCase):
    def test_columns(self):
        self.assertEqual(list(table().columns), OBS_FIELDS)

    def test_every_text_file_produces_an_observation(self):
        counts = table().file_id.value_counts()
        empty = [r.file_path for r in text_files().itertuples() if counts.get(r.file_id, 0) == 0]
        if empty:
            print("\nfiles with 0 observations:", *empty, sep="\n  ")
        self.assertEqual(empty, [])

    def test_every_regex_resource_id_is_parsed(self):
        missing = missing_resource_ids()
        if missing:
            print(f"\nresource ids found by regex but not parsed: {sum(missing.values())}")
            for f, n in missing.most_common(10):
                print(f"  {n:4d}  {f}")
        self.assertEqual(sum(missing.values()), 0)

    def test_no_missing_captured_at(self):
        self.assertFalse((table().captured_at == "").any())

    def test_identifiers_are_a_dict_of_sorted_lists(self):
        for ids in table().identifiers:
            self.assertEqual(sorted(ids), ["emails", "hashes", "phones", "user_ids"])
            for v in ids.values():
                self.assertEqual(v, sorted(set(v)))

    def test_snippet_length(self):
        self.assertTrue((table().raw_snippet.str.len() <= 200).all())

    def test_deterministic(self):
        a = observations.to_records(table())
        b = observations.to_records(observations.build_observations())
        self.assertEqual(a, b)

    def test_originals_untouched(self):
        before = digest_evidence()
        observations.build_observations()
        self.assertEqual(before, digest_evidence())


def missing_resource_ids():
    """Per file: regex-found resource ids that no observation of that file carries."""
    parsed = table().groupby("file_id").resource_id.agg(set).to_dict()
    missing = Counter()
    for r in text_files().itertuples():
        found = set(parse_common.RESOURCE_ID.findall(raw_text(EVIDENCE_DIR.parent / r.file_path)))
        missing[r.file_path] += len(found - parsed.get(r.file_id, set()))
    return +missing


def digest_evidence():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(EVIDENCE_DIR.rglob("*")) if p.is_file()}


if __name__ == "__main__":
    observations.print_summary(table())
    unittest.main(verbosity=1)
