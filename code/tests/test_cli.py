"""CLI behaviour without the Claude Code CLI: the run must succeed, say plainly that no
model call is made, and write the output.

Run:  python3 code/tests/test_cli.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]


class NoClaudeCliTest(unittest.TestCase):
    def test_runs_without_claude_and_says_so(self):
        if shutil.which("claude", path="/usr/bin:/bin"):
            self.skipTest("claude is on the minimal PATH")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "sample.csv"
            env = {"PATH": "/usr/bin:/bin", "HOME": d}
            proc = subprocess.run([sys.executable, str(CODE / "main.py"), "--sample", "--out", str(out)],
                                  env=env, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr[-500:])
            self.assertIn("Claude Code CLI not found", proc.stderr)
            self.assertEqual(len(out.read_text().splitlines()), 33)


class MissingEvidenceTest(unittest.TestCase):
    def test_missing_evidence_file_stops_the_run_with_a_clear_message(self):
        """A file listed in evidence_files.csv but absent must not yield an output built on a
        partial evidence picture: exit 1, name the file, write nothing, no traceback."""
        with tempfile.TemporaryDirectory() as d:
            ds = Path(d) / "dataset"
            shutil.copytree(CODE.parent / "dataset", ds)
            first = (ds / "evidence_files.csv").read_text().splitlines()[1].split(",")[1]
            (ds / first).unlink()
            out = Path(d) / "out.csv"
            proc = subprocess.run([sys.executable, str(CODE / "main.py"), "--no-llm", "--sample",
                                   "--dataset", str(ds), "--out", str(out)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("missing evidence", proc.stderr)
            self.assertIn(first, proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertFalse(out.exists())


class MalformedInputTest(unittest.TestCase):
    def run_main(self, ds, out):
        return subprocess.run([sys.executable, str(CODE / "main.py"), "--no-llm", "--sample",
                               "--dataset", str(ds), "--out", str(out)], capture_output=True, text=True)

    def test_wrong_header_and_bad_path_fail_with_a_clear_message(self):
        with tempfile.TemporaryDirectory() as d:
            ds = Path(d) / "dataset"
            shutil.copytree(CODE.parent / "dataset", ds)
            f = ds / "sample_deletion_requests.csv"
            f.write_text(f.read_text().replace("audit_at", "audit_time", 1))
            for target in (ds, Path(d) / "no_such_dir"):
                proc = self.run_main(target, Path(d) / "out.csv")
                self.assertEqual(proc.returncode, 1)
                self.assertIn("ERROR:", proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)
                self.assertFalse((Path(d) / "out.csv").exists())

    def test_empty_request_text_still_gets_a_valid_row(self):
        with tempfile.TemporaryDirectory() as d:
            ds = Path(d) / "dataset"
            shutil.copytree(CODE.parent / "dataset", ds)
            f = ds / "sample_deletion_requests.csv"
            lines = f.read_text().splitlines()
            import csv as _csv, io
            rows = list(_csv.reader(io.StringIO("\n".join(lines))))
            rows[1][-1] = ""
            buf = io.StringIO(); _csv.writer(buf, lineterminator="\n").writerows(rows); f.write_text(buf.getvalue())
            out = Path(d) / "out.csv"
            proc = self.run_main(ds, out)
            self.assertEqual(proc.returncode, 0, proc.stderr[-400:])
            got = list(_csv.DictReader(out.open()))
            self.assertEqual(len(got), 32)
            self.assertIn(got[0]["deletion_status"], ("COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
