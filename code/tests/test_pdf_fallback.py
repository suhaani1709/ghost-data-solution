"""PDF text fallback: when the pdftotext binary is missing, parse_common.pdf_pages
reads the committed code/pdf_text/<file_id>.md instead and logs a warning.

Missing pdftotext is simulated by making shutil.which return None (unit level)
and by running main.py with a PATH that has no pdftotext (end to end). The
observations and output.csv must be identical either way.

Run:  python3 code/tests/test_pdf_fallback.py
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

CODE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE))

from ghost import loaders, observations, parse_common as pc  # noqa: E402

HAVE_PDFTOTEXT = shutil.which("pdftotext") is not None


def pdf_files():
    m = loaders.load_evidence_files()
    return [(f.file_id, loaders.DATASET_DIR / f.file_path) for f in m.itertuples()
            if f.file_path.lower().endswith(".pdf")]


class RoundTripTest(unittest.TestCase):
    def test_markdown_round_trip_is_exact(self):
        pages = ["Page one\n  col   col\n", "", "last page, no newline"]
        self.assertEqual(pc.md_to_pages(pc.pages_to_md(pages, "x.pdf")), pages)


class FallbackTest(unittest.TestCase):
    def test_every_pdf_has_committed_text(self):
        for file_id, _ in pdf_files():
            self.assertTrue((pc.PDF_TEXT_DIR / f"{file_id}.md").is_file(), file_id)

    def test_missing_binary_uses_committed_text_with_warning(self):
        file_id, path = pdf_files()[0]
        with mock.patch.object(pc.shutil, "which", return_value=None), \
                self.assertLogs(pc.log, "WARNING") as logs:
            pages = pc.pdf_pages(path, file_id=file_id)
        self.assertTrue(pages)
        self.assertIn(f"{file_id}.md", logs.output[0])

    def test_missing_binary_and_no_text_raises(self):
        with mock.patch.object(pc.shutil, "which", return_value=None), \
                self.assertRaises(RuntimeError):
            pc.pdf_pages(Path("nowhere.pdf"), file_id="no_such_file")

    @unittest.skipUnless(HAVE_PDFTOTEXT, "pdftotext not installed")
    def test_committed_text_equals_pdftotext(self):
        for file_id, path in pdf_files():
            with mock.patch.object(pc.shutil, "which", return_value=None), \
                    self.assertLogs(pc.log, "WARNING"):
                fallback = pc.pdf_pages(path, file_id=file_id)
            self.assertEqual(pc.pdf_pages(path, file_id=file_id), fallback, file_id)

    @unittest.skipUnless(HAVE_PDFTOTEXT, "pdftotext not installed")
    def test_observations_identical(self):
        live = observations.to_records(observations.build_observations(images=True))
        with mock.patch.object(pc.shutil, "which", return_value=None), \
                self.assertLogs(pc.log, "WARNING"):
            fallback = observations.to_records(observations.build_observations(images=True))
        self.assertEqual(live, fallback)


class SuiteWithoutPdftotextTest(unittest.TestCase):
    def test_parser_acceptance_tests_pass_without_pdftotext(self):
        import test_parsers
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(test_parsers.EvidenceAcceptanceTest)
        with mock.patch.object(pc.shutil, "which", return_value=None), \
                self.assertLogs(pc.log, "WARNING"):
            result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
        self.assertEqual((len(result.errors), len(result.failures)), (0, 0),
                         [str(t) for t, _ in result.errors + result.failures])


@unittest.skipUnless(HAVE_PDFTOTEXT, "pdftotext not installed")
class EndToEndTest(unittest.TestCase):
    def test_output_byte_identical_without_pdftotext(self):
        if shutil.which("pdftotext", path="/usr/bin:/bin"):
            self.skipTest("pdftotext is on the minimal PATH too")
        with tempfile.TemporaryDirectory() as d:
            outs = []
            for name, path_env in (("live", os.environ["PATH"]), ("fallback", "/usr/bin:/bin")):
                out = Path(d) / f"{name}.csv"
                env = dict(os.environ, PATH=path_env)
                proc = subprocess.run([sys.executable, str(CODE / "main.py"), "--offline", "--out", str(out)],
                                      env=env, capture_output=True, text=True, check=True)
                outs.append((out.read_bytes(), proc.stderr))
            self.assertEqual(outs[0][0], outs[1][0])
            self.assertNotIn("pdftotext not found", outs[0][1])
            self.assertIn("pdftotext not found", outs[1][1])


if __name__ == "__main__":
    unittest.main(verbosity=1)
