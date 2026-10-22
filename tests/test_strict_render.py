"""Render contracts taken from the approved email component reference."""
from html.parser import HTMLParser
import json
import re
import unittest
from urllib.parse import parse_qs, urlsplit

from render_fixtures import fixture_models, render_fixture


class Node:
    def __init__(self, tag, attrs=(), parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.children, self.comments = [], []
        self.text = ""

    def find(self, tag=None, cls=None):
        result = []
        for child in self.children:
            if ((tag is None or child.tag == tag)
                    and (cls is None or cls in child.attrs.get("class", "").split())):
                result.append(child)
            result.extend(child.find(tag, cls))
        return result


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.root = self.current = Node("root")
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in {"meta", "link", "br", "img", "hr", "input"}:
            self.current = node

    def handle_endtag(self, tag):
        if self.current.tag == tag:
            self.current = self.current.parent

    def handle_data(self, data):
        self.current.text += data

    def handle_comment(self, data):
        self.current.comments.append(data)


def render_tree(digest, model=None):
    _, html = render_fixture(digest, model or fixture_models()[digest])
    return Document(html).root


def chart_config(image):
    config = parse_qs(urlsplit(image.attrs["src"]).query)["c"][0]
    # QuickChart accepts JavaScript callbacks; quote just those for JSON inspection.
    config = re.sub(r"function\(v\)\{return v\.toFixed\(\d+\)\+'%'\}",
                    lambda match: json.dumps(match.group()), config)
    return json.loads(config)


class StrictRenderTests(unittest.TestCase):
    def test_headers_have_only_template_eyebrow_title_lead_and_rule_rows(self):
        for digest in ("revenue", "reviews", "conversion"):
            with self.subTest(digest=digest):
                tree = render_tree(digest)
                header = tree.find("h1")[0].parent.parent.parent
                cells = [row.children[0] for row in header.children]
                self.assertEqual([cell.attrs["style"] for cell in cells], [
                    "padding:40px 40px 10px 40px; text-align:left;",
                    "padding:10px 40px 0 40px;",
                    "padding:16px 40px 0 40px;",
                    "padding:24px 40px 0 40px;",
                ])

    def test_body_sections_use_template_spacing_and_four_column_stat_cells(self):
        for digest in ("revenue", "reviews", "conversion"):
            with self.subTest(digest=digest):
                tree = render_tree(digest)
                body_cells = tree.find("td", "body-cell")[4:]
                for cell in body_cells:
                    if "footer-bg" in cell.attrs.get("class", ""):
                        continue
                    expected_top = "32px" if any(c.tag == "h2" for c in cell.children) else "16px"
                    self.assertTrue(cell.attrs["style"].startswith(f"padding:{expected_top} 40px 0 40px;"), cell.attrs)
                columns = tree.find("div", "stat-col")
                self.assertTrue(columns)
                for column in columns:
                    parent = column.parent
                    self.assertEqual(parent.tag, "td")
                    self.assertEqual(parent.attrs["style"], "padding:16px 40px 0 40px; font-size:0; text-align:center;")
                    self.assertEqual(len(parent.find("div", "stat-col")), 4)
                    intro = parent.children[0]
                    self.assertEqual(intro.tag, "p")
                    self.assertIn("Margin:0 0 20px 0;", intro.attrs["style"])
                    self.assertIn("text-align:left;", intro.attrs["style"])
                    ghost = "".join(parent.comments)
                    self.assertIn('width="520" align="center"', ghost)
                    self.assertEqual(ghost.count('<td valign="top" width="130" align="center">'), 4)

    def test_footers_include_description_links_and_metadata_in_template_sizes(self):
        for digest in ("revenue", "reviews", "conversion"):
            with self.subTest(digest=digest):
                footer = render_tree(digest).find("td", "footer-bg")[0]
                self.assertEqual(footer.attrs["style"], "background-color:#ece9e6; padding:32px 40px; border-radius:0 0 6px 6px;")
                paragraphs = footer.find("p")
                self.assertEqual(len(paragraphs), 4)
                self.assertEqual([re.search(r"font-size:(\d+)px", p.attrs["style"]).group(1)
                                  for p in paragraphs], ["13", "12", "12", "11"])
                self.assertTrue(paragraphs[2].find("a", "email-link"))

    def test_review_cards_use_text_card_container_and_typography(self):
        tree = render_tree("reviews")
        cards = tree.find("td", "card-bg")
        self.assertEqual(len(cards), 2)
        for card in cards:
            self.assertEqual(card.attrs["bgcolor"], "#fefefe")
            self.assertEqual(card.attrs["style"], "background-color:#fefefe; padding:24px; border-radius:6px;")
            self.assertEqual(card.parent.parent.attrs["style"], "border-radius:6px; box-shadow:0 2px 8px rgba(0,0,0,0.08);")
            heading = card.find("h4", "heading-dm")[0]
            self.assertIn("Margin:0 0 8px 0;", heading.attrs["style"])
            self.assertIn("font-size:16px; font-weight:600; line-height:1.4; color:#222222;", heading.attrs["style"])
            body = card.find("p", "text-main")[0]
            self.assertIn("Margin:0 0 12px 0;", body.attrs["style"])
            self.assertIn("font-size:15px; line-height:1.6; color:#222222;", body.attrs["style"])

    def test_charts_use_template_figure_and_requested_palette(self):
        for image in render_tree("conversion").find("img"):
            self.assertEqual(image.attrs.get("class"), "fluid")
            self.assertEqual(image.attrs["style"], "display:block; width:100%; max-width:520px; height:auto; border-radius:4px;")
            self.assertEqual(image.parent.attrs["style"], "padding:0;")
            figure = image.parent.parent.parent
            caption = figure.children[1].children[0]
            self.assertIn("Daily install→paid rate, last 2 cohorts", caption.text)
            self.assertIn("font-size:13px; line-height:1.4; color:#666666; text-align:center;", caption.attrs["style"])
            config = chart_config(image)
            dataset = config["data"]["datasets"][0]
            self.assertEqual(dataset["borderColor"], "#222222")
            self.assertEqual(dataset["pointBackgroundColor"][-1], "#c0392b")
            self.assertEqual(parse_qs(urlsplit(image.attrs["src"]).query)["bkg"], ["#ffffff"])
            for axis in ("xAxes", "yAxes"):
                spec = config["options"]["scales"][axis][0]
                self.assertEqual(spec["ticks"]["fontColor"], "#777777")
                self.assertIn("Inter", spec["ticks"]["fontFamily"])
                self.assertIn("Segoe", spec["ticks"]["fontFamily"])
            self.assertEqual(config["options"]["scales"]["yAxes"][0]["gridLines"]["color"], "#dddddd")

    def test_flat_and_narrow_chart_ranges_never_repeat_y_tick_labels(self):
        for rates in ([3.0, 3.02], [3.21, 3.21], [0.0, 0.0], [1.0, 1.7], [2.0, 12.0]):
            with self.subTest(rates=rates):
                model = fixture_models()["conversion"]
                model["apps"] = model["apps"][:1]
                for cohort, rate in zip(model["apps"][0]["cohorts"], rates):
                    cohort["rate"] = rate
                config = chart_config(render_tree("conversion", model).find("img")[0])
                ticks = config["options"]["scales"]["yAxes"][0]["ticks"]
                precision = int(re.search(r"toFixed\((\d+)\)", ticks["callback"]).group(1))
                self.assertIn("stepSize", ticks)
                self.assertGreater(ticks["stepSize"], 0)
                self.assertLess(ticks["min"], ticks["max"])
                self.assertLessEqual(ticks["min"], min(rates))
                self.assertGreaterEqual(ticks["max"], max(rates))
                count = round((ticks["max"] - ticks["min"]) / ticks["stepSize"]) + 1
                labels = [f"{ticks['min'] + index * ticks['stepSize']:.{precision}f}%" for index in range(count)]
                self.assertEqual(len(labels), len(set(labels)))
                self.assertGreaterEqual(count, 2)


if __name__ == "__main__":
    unittest.main()
