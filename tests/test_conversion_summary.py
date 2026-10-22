"""The header summary keeps every app's current rate visible at a glance."""
import unittest

from render_fixtures import fixture_models
from test_strict_render import render_tree
from scripts.common import email_shell as shell


class ConversionSummaryTests(unittest.TestCase):
    def summary_cards(self, tree, expected_count):
        # The four masthead cells end with the header rule. The next content
        # cell must be the summary, before the first per-app section heading.
        summary = tree.find("td", "body-cell")[4]
        cards = summary.find("td", "stat-card-dm")
        self.assertEqual(len(cards), expected_count)
        self.assertFalse(summary.find("h2"))
        self.assertIs(summary.parent.parent.children[0], summary.parent)
        return cards

    def test_summary_is_first_body_row_with_one_short_label_per_app(self):
        model = fixture_models()["conversion"]
        tree = render_tree("conversion", model)
        cards = self.summary_cards(tree, len(model["apps"]))
        labels = [card.find("p", "stat-label-dm")[0] for card in cards]
        self.assertEqual([label.text for label in labels], ["MARINE", "RULER", "GEO"])
        self.assertEqual([card.find("p", "stat-value")[0].text for card in cards],
                         ["3.2%", "5.5%", "0.0%"])
        for label in labels:
            self.assertLessEqual(len(label.text), 10)
            self.assertIn("font-size:11px;", label.attrs["style"])
            self.assertIn("text-transform:uppercase;", label.attrs["style"])

    def test_summary_rate_colors_include_threshold_boundaries_and_no_data(self):
        for rates, colors in [
            ([1.9, 2.0, 4.9], [shell.RED, shell.AMBER, shell.AMBER]),
            ([5.0, 7.5, 0.0], [shell.GREEN, shell.GREEN, shell.RED]),
        ]:
            with self.subTest(rates=rates):
                model = fixture_models()["conversion"]
                # The configured spelling and fixture spelling both map to
                # the same readable summary label.
                model["apps"][1]["name"] = "SmartRuler"
                for app, rate in zip(model["apps"], rates):
                    app["overall_rate"] = rate
                cards = self.summary_cards(render_tree("conversion", model), 3)
                for card, rate, color in zip(cards, rates, colors):
                    value = card.find("p", "stat-value")[0]
                    self.assertEqual(value.text, f"{rate:.1f}%")
                    self.assertIn(f"color:{color};", value.attrs["style"])
                self.assertEqual(cards[1].find("p", "stat-label-dm")[0].text, "RULER")

    def test_per_app_stats_and_bar_charts_follow_summary(self):
        model = fixture_models()["conversion"]
        tree = render_tree("conversion", model)
        self.summary_cards(tree, 3)
        cells = tree.find("td", "body-cell")[5:]
        headings = [cell for cell in cells if cell.find("h2")]
        self.assertEqual([cell.find("h2")[0].text for cell in headings],
                         ["MarineRadar", "Smart Ruler", "GeoAnimator", "Conversion dashboard"])
        for app, heading in zip(model["apps"], headings):
            index = cells.index(heading)
            following = cells[index + 1]
            if app["has_data"]:
                self.assertEqual([label.text for label in following.find("p", "stat-label-dm")],
                                 ["Rate", "Installs", "Paid", "Cohort days"])
                self.assertEqual([value.text for value in following.find("p", "stat-value")],
                                 [f"{app['overall_rate']:.1f}%", "1,000",
                                  str(app["total_paid"]), "2"])
                chart = cells[index + 2].find("table", "bar-chart-dm")
                self.assertEqual(len(chart), 1)
                self.assertEqual([label.text for label in chart[0].find("td", "bar-label-dm")],
                                 ["Oct 19", "Oct 20"])
            else:
                self.assertFalse(following.find("td", "stat-cell"))
                self.assertFalse(following.find("table", "bar-chart-dm"))
        self.assertEqual(len(tree.find("table", "bar-chart-dm")), 2)
        self.assertFalse(tree.find("img"))


if __name__ == "__main__":
    unittest.main()
