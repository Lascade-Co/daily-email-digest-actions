"""Keep the vendored shell identical to the approved mobile email shell."""
from hashlib import sha256
from pathlib import Path
import unittest

from test_strict_render import Document
from render_fixtures import mobile_fixture_models, render_fixture
from scripts.common import email_shell as shell


class ShellSyncTests(unittest.TestCase):
    def test_copy_has_exact_headers_and_approved_canonical_hash(self):
        copy = Path(shell.__file__).read_bytes()
        notice, hash_line, canonical = copy.split(b"\n", 2)
        self.assertEqual(notice.decode(),
                         "# COPY of product-intelligence/Style Template/email_shell.py "
                         "— edit the canonical file, then re-copy.")
        self.assertEqual(hash_line, b"# sha256(canonical) = dd15638edbe2")
        self.assertEqual(sha256(canonical).hexdigest(),
                         "dd15638edbe24645d912af5477383f3f9a9045a0b84d39ab46eed2a1fb5972a6")

    def test_configured_three_column_survey_headers_allow_whole_word_wrapping(self):
        models = mobile_fixture_models()
        expected_headers = {
            "survey_measure": ["Status", "Got measurement?", "Blocker"],
            "survey_marine": ["Issues faced", "Feature request", "Frequency"],
        }
        for digest, expected in expected_headers.items():
            with self.subTest(digest=digest):
                _, html = render_fixture(digest, models[digest])
                headers = Document(html).root.find("th")[:3]
                self.assertEqual([header.text for header in headers], expected)
                for header in headers:
                    self.assertNotIn("white-space:nowrap", header.attrs["style"])
                    self.assertIn("word-break:normal;", header.attrs["style"])
                    self.assertIn("overflow-wrap:normal;", header.attrs["style"])
                    self.assertIn("hyphens:none;", header.attrs["style"])

    def test_three_stat_cards_share_a_row_and_four_form_two_rows(self):
        for count, expected in ((3, [3]), (4, [2, 2])):
            with self.subTest(count=count):
                html = shell.stat_grid([(i, f"Metric {i}", shell.INK) for i in range(count)])
                rows = Document(html).root.find("table", "stat-row")
                self.assertEqual([len(row.find("td", "stat-cell")) for row in rows], expected)
                for row in rows:
                    self.assertIn("table-layout:fixed;", row.attrs["style"])

    def test_semantic_badges_use_guide_colors(self):
        for variant, color in (("critical", "#c0392b"), ("warning", "#8a6520"),
                               ("positive", "#2a8c4a"), ("info", "#2980b9")):
            with self.subTest(variant=variant):
                self.assertIn(f"color:{color};", shell.badge("Status", variant))


if __name__ == "__main__":
    unittest.main()
