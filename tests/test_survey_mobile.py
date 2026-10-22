"""Keep survey fields and response counts readable in narrow email clients."""
import unittest

from scripts.survey import survey_render
from test_strict_render import Document


def response_section(columns, rows, has_status=False):
    return {
        "columns": columns,
        "has_status": has_status,
        "rows": [
            {"status_label": "Pro", "cells": [{"value": value} for value in row]}
            for row in rows
        ],
    }


class SurveyMobileTests(unittest.TestCase):
    def test_four_or_more_columns_render_one_record_per_row(self):
        columns = ["Submission", "IMO", "Type", "Country", "Details"]
        values = ["Britannic <ship> & fleet", "1234567", "Passenger ship",
                  "United Kingdom", "Add <route> details & ports"]
        for count in (4, 5):
            with self.subTest(columns=count):
                html = survey_render._response_table(response_section(
                    columns[:count], [values[:count]],
                ))
                table = Document(html).root.find("table")[0]
                self.assertEqual([header.text for header in table.find("th")], ["Submission"])
                cells = table.find("td")
                self.assertEqual(len(cells), 1)
                self.assertEqual(cells[0].find("strong")[0].text, "Britannic <ship> & fleet")
                self.assertEqual(len(cells[0].find("br")), 1)
                caption = cells[0].find("span", "text-muted")[0]
                expected_caption = "IMO 1234567 · Type: Passenger ship · Country: United Kingdom"
                if count == 5:
                    expected_caption += " · Details: Add <route> details & ports"
                self.assertEqual(caption.text, expected_caption)
                self.assertIn("font-size:13px;", caption.attrs["style"])
                self.assertIn("color:#666666;", caption.attrs["style"])
                self.assertNotIn("<ship>", html)
                self.assertNotIn("<route>", html)

    def test_record_fields_skip_blank_values_and_keep_response_order(self):
        html = survey_render._response_table(response_section(
            ["Vessel", "IMO", "Type", "Country", "Details"],
            [
                ["", " — ", "Frigate", "Britain", ""],
                ["Calypso", "", "—", None, ""],
                ["", "—", "", "", ""],
                ["Zero", 0, "", "", ""],
            ],
        ))
        cells = Document(html).root.find("table")[0].find("td")
        self.assertEqual(len(cells), 4)
        self.assertEqual(cells[0].find("strong")[0].text, "Type: Frigate")
        self.assertEqual(cells[0].find("span", "text-muted")[0].text, "Country: Britain")
        self.assertEqual(cells[1].find("strong")[0].text, "Calypso")
        self.assertFalse(cells[1].find("span"))
        self.assertFalse(cells[1].find("br"))
        self.assertEqual(cells[2].text, "")
        self.assertFalse(cells[2].children)
        self.assertEqual(cells[3].find("strong")[0].text, "Zero")
        self.assertEqual(cells[3].find("span", "text-muted")[0].text, "IMO 0")
        self.assertNotIn("—", html)

    def test_blank_vessel_primary_keeps_the_imo_label(self):
        for blank in ("", "  ", "—", " — ", None):
            with self.subTest(vessel=blank):
                html = survey_render._response_table(response_section(
                    ["Vessel", "IMO", "Type", "Country", "Details"],
                    [[blank, "9876543", "tanker", "Benin", "—"]],
                ))
                table = Document(html).root.find("table")[0]
                self.assertEqual([header.text for header in table.find("th")], ["Vessel"])
                self.assertEqual(table.find("strong")[0].text, "IMO 9876543")
                self.assertEqual(table.find("span", "text-muted")[0].text,
                                 "Type: tanker · Country: Benin")

    def test_fallback_primary_escapes_its_original_label_and_value(self):
        html = survey_render._response_table(response_section(
            ["Vessel", 'IM<O> & "code"', "Type", "Country"],
            [[None, "1 <2> & 3", "—", ""]],
        ))
        cell = Document(html).root.find("table")[0].find("td")[0]
        primary = cell.find("strong")[0]
        self.assertEqual(primary.text, 'IM<O> & "code": 1 <2> & 3')
        self.assertFalse(primary.children)
        self.assertIn('<strong>IM&lt;O&gt; &amp; &quot;code&quot;: 1 &lt;2&gt; &amp; 3</strong>', html)
        self.assertFalse(cell.find("span"))

    def test_record_captions_escape_labels_and_keep_labels_with_nonempty_values(self):
        html = survey_render._response_table(response_section(
            ["Submission", 'IM<O> & "code"', "Type", "Country", "Details"],
            [["Test vessel", "1 <2> & 3", "", "France", "—"]],
        ))
        cell = Document(html).root.find("table")[0].find("td")[0]
        self.assertEqual(cell.find("strong")[0].text, "Test vessel")
        caption = cell.find("span", "text-muted")[0]
        self.assertEqual(caption.text, 'IM<O> & "code": 1 <2> & 3 · Country: France')
        self.assertFalse(caption.children)
        self.assertIn('IM&lt;O&gt; &amp; &quot;code&quot;: 1 &lt;2&gt; &amp; 3', html)
        self.assertNotIn("Type:", html)
        self.assertNotIn("Details:", html)

    def test_status_counts_toward_four_column_threshold_and_keeps_its_order(self):
        html = survey_render._response_table(response_section(
            ["Feedback", "Score", "Frequency"],
            [["More routes", "4/5", "Daily"]],
            has_status=True,
        ))
        table = Document(html).root.find("table")[0]
        self.assertEqual([header.text for header in table.find("th")], ["Status"])
        self.assertEqual(table.find("strong")[0].text, "Pro")
        self.assertEqual(table.find("span", "text-muted")[0].text,
                         "Feedback: More routes · Score: 4/5 · Frequency: Daily")

    def test_three_columns_keep_the_existing_table_layout(self):
        html = survey_render._response_table(response_section(
            ["Feedback", "Score"], [["More <routes> & ports", "4/5"]],
            has_status=True,
        ))
        table = Document(html).root.find("table")[0]
        self.assertEqual([header.text for header in table.find("th")], ["Status", "Feedback", "Score"])
        self.assertEqual([cell.text for cell in table.find("td")], ["Pro", "More <routes> & ports", "4/5"])
        self.assertFalse(table.find("strong"))
        self.assertNotIn("<routes>", html)

    def test_grouped_theme_count_has_fixed_width_with_flexible_theme_column(self):
        html = survey_render._summary({
            "header": "Requests", "type": "grouped",
            "groups": [{"text": "Missing ship requests", "count": 12}],
        })
        headers = Document(html).root.find("th")
        self.assertEqual([header.text for header in headers], ["Response theme", "Count"])
        self.assertEqual(headers[1].attrs.get("width"), "72")
        self.assertEqual(headers[1].attrs["align"], "right")
        self.assertNotIn("width", headers[0].attrs)
        self.assertEqual([cell.text for cell in Document(html).root.find("table")[0].find("td")],
                         ["Missing ship requests", "12"])


if __name__ == "__main__":
    unittest.main()
