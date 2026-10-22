"""Keep digest stat labels compact without changing the template typography."""
import unittest

from test_strict_render import render_tree


class StatLabelTests(unittest.TestCase):
    def test_rendered_stat_labels_are_at_most_14_characters(self):
        for digest in ("conversion", "revenue", "reviews"):
            columns = render_tree(digest).find("div", "stat-col")
            self.assertTrue(columns)
            for column in columns:
                labels = column.find("p", "stat-label-dm")
                self.assertEqual(len(labels), 1)
                label = labels[0]
                with self.subTest(digest=digest, label=label.text):
                    self.assertLessEqual(len(label.text.strip().upper()), 14)
                    self.assertFalse(label.children)
                    self.assertIn("font-size:11px;", label.attrs["style"])
                    self.assertIn("text-transform:uppercase;", label.attrs["style"])
                    self.assertIn("max-width:130px;", column.attrs["style"])


if __name__ == "__main__":
    unittest.main()
