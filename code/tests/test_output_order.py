"""Output row order: numeric case order, the order of deletion_requests.csv.

String order puts case_100 before case_33; the request file (and any grader
that pairs rows by position) uses case_33, case_34, ..., case_550.

Run:  python3 code/tests/test_output_order.py
"""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evaluation"))

import validate  # noqa: E402
from ghost import loaders  # noqa: E402

IDS = ["case_100", "case_33", "case_9", "case_10"]


class OutputOrderTest(unittest.TestCase):
    def test_numeric_case_order(self):
        self.assertEqual(loaders.sort_case_ids(IDS), ["case_9", "case_10", "case_33", "case_100"])
        self.assertEqual(loaders.sort_case_ids(["case_02", "case_10", "case_01"]),
                         ["case_01", "case_02", "case_10"])

    def test_request_file_is_in_numeric_order(self):
        ids = list(loaders.load_deletion_requests().case_id)
        self.assertEqual(ids, loaders.sort_case_ids(ids))

    def test_validator_rejects_string_order(self):
        requests = pd.DataFrame({"case_id": IDS, "audit_at": ["2026-01-02T00:00:00Z"] * 4})
        manifest = pd.DataFrame({"file_id": [], "captured_at": []})
        for order, bad in ((sorted(IDS), True), (loaders.sort_case_ids(IDS), False)):
            with tempfile.TemporaryDirectory() as d:
                path = Path(d) / "out.csv"
                with open(path, "w", newline="", encoding="utf-8") as fh:
                    w = csv.writer(fh)
                    w.writerow(loaders.OUTPUT_COLUMNS)
                    w.writerows((c, "NOT_APPLICABLE", "[]") for c in order)
                _, errors, _, _, _ = validate.validate(path, requests, manifest, set(), {})
            self.assertEqual("rows not in numeric case_id order" in errors, bad, order)


class LineEndingTest(unittest.TestCase):
    def test_output_uses_lf_like_the_dataset_files(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import importlib.util
        spec = importlib.util.spec_from_file_location("ghost_main", Path(__file__).resolve().parents[1] / "main.py")
        main_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(main_mod)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "out.csv"
            main_mod.write_output([{"case_id": "case_1", "deletion_status": "NOT_APPLICABLE", "steps_json": "[]"}], path)
            self.assertEqual(path.read_bytes(), b"case_id,deletion_status,steps_json\ncase_1,NOT_APPLICABLE,[]\n")


if __name__ == "__main__":
    unittest.main(verbosity=1)
