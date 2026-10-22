"""Reserve enough mobile table width for complete survey header words."""
import unittest

from render_fixtures import fixture_models, mobile_fixture_models, render_fixture
from scripts.survey import survey_render
from test_strict_render import Document


class SurveyWidthTests(unittest.TestCase):
    def test_every_fixture_table_fits_its_longest_header_words_at_393px(self):
        for fixture_name, models in (("standard", fixture_models()),
                                     ("mobile", mobile_fixture_models())):
            for digest in ("survey_marine", "survey_measure"):
                _, html = render_fixture(digest, models[digest])
                tables_checked = 0
                for table in Document(html).root.find("table"):
                    headers = [header for header in table.find("th")
                               if header.parent.parent is table]
                    if not headers:
                        continue
                    tables_checked += 1
                    labels = [header.text for header in headers]
                    with self.subTest(fixture=fixture_name, digest=digest, headers=labels):
                        if len(headers) in (2, 3) and labels != ["Response theme", "Count"]:
                            self.assertTrue(all(header.attrs.get("width") for header in headers))
                        widths = []
                        for header in headers:
                            width = header.attrs.get("width")
                            widths.append(None if not width else
                                          float(width[:-1]) * 333 / 100 if width.endswith("%")
                                          else float(width))
                        flexible = widths.count(None)
                        remaining = 333 - sum(width for width in widths if width is not None)
                        resolved = [remaining / flexible if width is None else width for width in widths]
                        self.assertAlmostEqual(sum(resolved), 333, places=4)
                        for header, width in zip(headers, resolved):
                            longest_word = max(len(word) for word in header.text.upper().split())
                            self.assertGreaterEqual(width, longest_word * 9.5 + 24, header.text)
                self.assertGreater(tables_checked, 0)

    def test_two_column_response_table_gives_spare_width_to_feedback(self):
        html = survey_render._response_table({
            "has_status": False, "columns": ["Feedback", "Score"],
            "rows": [{"cells": [{"value": "More harbor alerts"}, {"value": "4/5"}]}],
        })
        headers = Document(html).root.find("th")
        self.assertTrue(all(header.attrs.get("width", "").endswith("%") for header in headers))
        pixels = [float(header.attrs["width"][:-1]) * 333 / 100 for header in headers]
        self.assertGreater(pixels[0], 250)
        self.assertGreaterEqual(pixels[1], 71.5)
        self.assertLess(pixels[1], 72)

    def test_three_column_response_table_reserves_choice_headers_and_expands_blocker(self):
        html = survey_render._response_table({
            "has_status": True, "columns": ["Got measurement?", "Blocker"],
            "rows": [{"status_label": "Free", "cells": [
                {"value": "Not yet"}, {"value": "Could not find a flat surface"},
            ]}],
        })
        headers = Document(html).root.find("th")
        self.assertTrue(all(header.attrs.get("width", "").endswith("%") for header in headers))
        pixels = [float(header.attrs["width"][:-1]) * 333 / 100 for header in headers]
        self.assertGreaterEqual(pixels[0], 81)
        self.assertLess(pixels[0], 82)
        self.assertGreaterEqual(pixels[1], 138)
        self.assertLess(pixels[1], 139)
        self.assertGreater(pixels[2], 113)
        self.assertAlmostEqual(sum(pixels), 333, places=4)


if __name__ == "__main__":
    unittest.main()
