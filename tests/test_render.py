"""Renderer behavior: metric tails, safe text, and usable email structure."""
from html.parser import HTMLParser
import unittest

from render_fixtures import fixture_models, render_fixture


class ImagesInBodyCells(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cells = []
        self.images = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "td":
            self.cells.append("body-cell" in attrs.get("class", "").split())
        elif tag == "img":
            self.images.append((attrs, any(self.cells)))

    def handle_endtag(self, tag):
        if tag == "td" and self.cells:
            self.cells.pop()


class RenderTests(unittest.TestCase):
    def test_render_returns_only_the_metric_tail_for_subject_composition(self):
        expected = {
            "revenue": "$412.00 (3 purchases)",
            "reviews": "2 reviews with 3★ or under",
            "survey_marine": "8 new responses",
            "survey_measure": "8 new responses",
            "conversion": "MarineRadar 3.2%, Smart Ruler 5.5%",
        }
        for digest, model in fixture_models().items():
            with self.subTest(digest=digest):
                tail, _ = render_fixture(digest, model)
                self.assertEqual(tail, expected[digest])

    def test_every_digest_has_the_shared_accessible_dark_mode_shell(self):
        for digest, model in fixture_models().items():
            with self.subTest(digest=digest):
                _, html = render_fixture(digest, model)
                self.assertIn('content="light dark"', html)
                self.assertIn("prefers-color-scheme: dark", html)
                self.assertIn("[data-ogsc]", html)
                self.assertIn('class="email-h1 heading-dm text-main"', html)
                self.assertEqual(html.count("<head>"), 1)
                self.assertEqual(html.count("</body>"), 1)

    def test_revenue_retains_daily_refunds_packs_and_month_net(self):
        _, html = render_fixture("revenue", fixture_models()["revenue"])
        for text in ("$412.00", "$29.00", "$198.00", "$3,830.00", "Credit Pack Breakdown", "Month to Date"):
            self.assertIn(text, html)

    def test_reviews_keep_store_metadata_and_escape_customer_text(self):
        _, html = render_fixture("reviews", fixture_models()["reviews"])
        for text in ("App Store", "Play Store", "United States", "Android 16", "2.4.0",
                     "Non-English", "No new reviews", "Route &lt;script&gt; &amp; chart",
                     "Please retain &lt;waypoints&gt; &amp; route history."):
            self.assertIn(text, html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<waypoints>", html)

    def test_survey_preserves_table_distribution_score_and_grouped_responses(self):
        models = fixture_models()
        for digest, product in (("survey_marine", "MarineRadar"), ("survey_measure", "Smart Ruler")):
            with self.subTest(digest=digest):
                _, html = render_fixture(digest, models[digest])
                for text in (product, "More &lt;routes&gt; &amp; ports", "4/5", "Live map",
                             "67%", "4.3/5", "Add &lt;harbor&gt; alerts &amp; weather",
                             "No meaningful responses", "View all in Sheets"):
                    self.assertIn(text, html)
                self.assertNotIn("<routes>", html)

    def test_conversion_keeps_quickchart_images_inside_body_cells(self):
        _, html = render_fixture("conversion", fixture_models()["conversion"])
        parsed = ImagesInBodyCells()
        parsed.feed(html)
        self.assertEqual(len(parsed.images), 2)
        for attrs, inside_body_cell in parsed.images:
            self.assertTrue(inside_body_cell)
            self.assertTrue(attrs["src"].startswith("https://quickchart.io/chart?c="))
            self.assertIn("conversion:", attrs["alt"])
        for text in ("32 paid", "1,000 installs", "GeoAnimator"):
            self.assertIn(text, html)


if __name__ == "__main__":
    unittest.main()
