"""Conversion chart contracts from the email reference's Bar Chart component."""
from datetime import date, timedelta
import unittest

from render_fixtures import fixture_models, render_fixture
from scripts.conversion import conversion_render
from test_strict_render import Document, render_tree


HEADING_FONT = "'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif"
FILL_FONT = "'Inter', system-ui, sans-serif"
TABLE_ATTRS = {
    "role": "presentation", "cellspacing": "0", "cellpadding": "0",
    "border": "0", "width": "100%",
}


def fill_cells(chart):
    return [track.children[0].children[0]
            for track in chart.find("table", "bar-track-dm")]


def width_percent(cell):
    return float(cell.attrs["width"].removesuffix("%"))


class ConversionBarTests(unittest.TestCase):
    def test_helper_matches_template_tables_labels_tracks_and_fills(self):
        html = conversion_render.bar_chart("Install → paid by cohort day", [
            ("Oct 20", "1.25%", 0.25), ("Oct 21", "5.00%", 1.0),
        ])
        charts = Document(html).root.find("table", "bar-chart-dm")
        self.assertEqual(len(charts), 1)
        chart = charts[0]
        self.assertEqual(chart.attrs, dict(TABLE_ATTRS, bgcolor="#fefefe",
            style="background-color:#fefefe; padding:0;", **{"class": "bar-chart-dm"}))
        content = chart.children[0].children[0]
        self.assertEqual(content.attrs, {"style": "padding:20px;"})
        title = content.children[0]
        self.assertEqual(title.tag, "p")
        self.assertEqual(title.text.strip(), "Install → paid by cohort day")
        self.assertEqual(title.attrs, {
            "class": "bar-title-dm",
            "style": "margin:0; Margin:0 0 12px 0; "
                f"font-family:{HEADING_FONT}; font-size:11px; font-weight:600; "
                "text-transform:uppercase; letter-spacing:0.06em; color:#999999;",
        })
        rows = content.children[1:]
        self.assertEqual(len(rows), 2)
        for index, row in enumerate(rows):
            with self.subTest(row=index):
                self.assertEqual(row.tag, "table")
                expected = dict(TABLE_ATTRS)
                if index == 0:
                    expected["style"] = "margin-bottom:8px;"
                self.assertEqual(row.attrs, expected)
                label, bar = row.children[0].children
                self.assertEqual(label.attrs, {
                    "width": "130", "class": "bar-label-cell bar-label-dm",
                    "style": f"font-family:{HEADING_FONT}; font-size:12px; "
                        "font-weight:600; color:#444444; text-align:right; "
                        "padding-right:10px; vertical-align:middle;",
                })
                self.assertEqual(label.text.strip(), ("Oct 20", "Oct 21")[index])
                self.assertEqual(bar.attrs, {"style": "vertical-align:middle;"})
                track = bar.children[0]
                self.assertEqual(track.attrs, dict(TABLE_ATTRS, bgcolor="#f0eeec",
                    style="background-color:#f0eeec;", **{"class": "bar-track-dm"}))
                fill, remainder = track.children[0].children
                color = ("#222222", "#c0392b")[index]
                self.assertEqual(fill.attrs["bgcolor"], color)
                self.assertEqual(fill.attrs["style"], f"background-color:{color}; "
                    f"height:28px; padding-left:8px; font-family:{FILL_FONT}; "
                    "font-size:11px; font-weight:700; color:#ffffff;")
                self.assertNotIn("class", fill.attrs)
                self.assertAlmostEqual(width_percent(fill), (25, 100)[index])
                self.assertAlmostEqual(width_percent(remainder), (75, 0)[index])
                self.assertEqual(fill.text.strip(), ("1.25%", "5.00%")[index])

    def test_helper_escapes_all_text_arguments(self):
        title, label, value = '<title> & "title"', '<label> & "label"', '<value> & "value"'
        html = conversion_render.bar_chart(title, [(label, value, 0.5)])
        tree = Document(html).root
        self.assertEqual(tree.find("p", "bar-title-dm")[0].text, title)
        self.assertEqual(tree.find("td", "bar-label-dm")[0].text, label)
        self.assertEqual(fill_cells(tree)[0].text, value)
        for tag in ("title", "label", "value"):
            self.assertFalse(tree.find(tag))
            self.assertIn(f"&lt;{tag}&gt;", html)

    def test_newest_seven_cohorts_sort_by_day_and_scale_to_visible_maximum(self):
        model = fixture_models()["conversion"]
        model["apps"] = model["apps"][:1]
        prototype = model["apps"][0]["cohorts"][0]
        cohorts = [dict(prototype,
            date=(date(2026, 10, 13) + timedelta(days=index)).isoformat(),
            rate=rate) for index, rate in enumerate([99, 20, 1, 2, 3, 4, 5, 6, 7])]
        model["apps"][0]["cohorts"] = [cohorts[i] for i in (8, 0, 5, 1, 7, 2, 6, 3, 4)]
        charts = render_tree("conversion", model).find("table", "bar-chart-dm")
        self.assertEqual(len(charts), 1)
        chart = charts[0]
        self.assertEqual([label.text.strip() for label in chart.find("td", "bar-label-dm")],
                         [f"Oct {day}" for day in range(15, 22)])
        fills = fill_cells(chart)
        self.assertEqual([fill.text.strip() for fill in fills],
                         [f"{rate:.2f}%" for rate in range(1, 8)])
        for rate, fill in enumerate(fills, 1):
            self.assertAlmostEqual(width_percent(fill), rate / 7 * 100, delta=0.01)
        self.assertEqual([fill.attrs["bgcolor"] for fill in fills],
                         ["#222222"] * 6 + ["#c0392b"])

    def test_one_chart_per_app_uses_body_cell_without_figure_or_images(self):
        model = fixture_models()["conversion"]
        _, html = render_fixture("conversion", model)
        tree = Document(html).root
        charts = tree.find("table", "bar-chart-dm")
        self.assertEqual(len(charts), 2)
        self.assertFalse(tree.find("img"))
        self.assertNotIn("quickchart", html.lower())
        self.assertNotIn("Daily install→paid rate, last", html)
        for chart in charts:
            self.assertEqual(chart.parent.tag, "td")
            self.assertEqual(chart.parent.attrs, {
                "style": "padding:16px 40px 0 40px;", "class": "body-cell",
            })
            self.assertEqual(chart.find("p", "bar-title-dm")[0].text.strip(),
                             "Install → paid by cohort day")
            self.assertEqual(max(width_percent(fill) for fill in fill_cells(chart)), 100)

    def test_zero_rates_keep_percentage_values_without_division_by_zero(self):
        model = fixture_models()["conversion"]
        model["apps"] = model["apps"][:1]
        for cohort in model["apps"][0]["cohorts"]:
            cohort["rate"] = 0.0
        charts = render_tree("conversion", model).find("table", "bar-chart-dm")
        self.assertEqual(len(charts), 1)
        fills = fill_cells(charts[0])
        self.assertEqual([fill.text.strip() for fill in fills], ["0.00%", "0.00%"])
        self.assertEqual([width_percent(fill) for fill in fills], [0, 0])
        self.assertEqual([fill.attrs["bgcolor"] for fill in fills], ["#222222", "#c0392b"])

    def test_single_cohort_renders_red_bar_with_two_decimal_percentage(self):
        for rate, width in ((1.2, 100), (0.0, 0)):
            with self.subTest(rate=rate):
                model = fixture_models()["conversion"]
                model["apps"] = model["apps"][:1]
                model["apps"][0]["cohorts"] = [dict(
                    model["apps"][0]["cohorts"][0], date="2026-11-01", rate=rate)]
                charts = render_tree("conversion", model).find("table", "bar-chart-dm")
                self.assertEqual(len(charts), 1)
                self.assertEqual(charts[0].find("td", "bar-label-dm")[0].text.strip(), "Nov 1")
                fills = fill_cells(charts[0])
                self.assertEqual(len(fills), 1)
                self.assertEqual(fills[0].text.strip(), f"{rate:.2f}%")
                self.assertEqual(fills[0].attrs["bgcolor"], "#c0392b")
                self.assertEqual(width_percent(fills[0]), width)


if __name__ == "__main__":
    unittest.main()
