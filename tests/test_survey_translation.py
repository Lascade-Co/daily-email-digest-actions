"""Survey translations preserve short feedback and expose failures safely."""
import base64
import contextlib
from datetime import datetime, timezone
import io
import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts.survey import survey_fetch, survey_main, survey_model, survey_render


ROOT = Path(__file__).resolve().parents[1]
START = datetime(2026, 11, 4, tzinfo=timezone.utc)
END = datetime(2026, 11, 5, tzinfo=timezone.utc)
STAMP = "2026-11-04T16:00:00Z"


def translated(text):
    values = {
        "卡顿": ("Lagging", "zh-CN", True),
        "Más puertos": ("More ports", "es", True),
        "Demasiado caro": ("Too expensive", "es", True),
        "Otro: avisos": ("Other: alerts", "es", True),
        "Le port manque": ("The port is missing", "fr", True),
    }
    return values.get(text, (text, "en", True))


def model_for(values, mode="table", columns=None, translate_fn=translated):
    config = {
        "product_name": "Survey", "sheet_url": "https://example.test/survey",
        "surveys": [{
            "sheet_name": "Answers", "label": "Feedback", "subtitle": "Responses",
            "render": mode,
            "columns": columns or [{"col": 1, "header": "Feedback"}],
        }],
    }
    rows = [[STAMP, *(value if isinstance(value, list) else [value])] for value in values]
    return survey_model.build_model(config, {"Answers": rows}, START, END, translate_fn)


class CloudTranslationTests(unittest.TestCase):
    def test_two_character_answer_uses_cloud_and_preserves_detected_language(self):
        response = Mock(status_code=200)
        response.json.return_value = {"data": {"translations": [{
            "translatedText": "Lagging", "detectedSourceLanguage": "zh-CN",
        }]}}
        with patch.object(survey_fetch, "_get_credentials", return_value=SimpleNamespace(token="test-token")), patch("requests.post", return_value=response):
            result = survey_fetch.translate_text({}, "卡顿")
        self.assertEqual(result, ("Lagging", "zh-CN", True))

    def test_cloud_failures_return_explicit_failure_without_logging_input_or_keys(self):
        source = "private survey answer"
        secret = "private service key"
        cases = [
            Mock(status_code=503),
            Mock(status_code=200, json=lambda: {"data": {"translations": []}}),
            Mock(status_code=200, json=lambda: {"data": {"translations": [{"translatedText": ""}]}}),
            RuntimeError(source + secret),
        ]
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        logging.getLogger().addHandler(handler)
        try:
            for case in cases:
                kwargs = {"side_effect": case} if isinstance(case, Exception) else {"return_value": case}
                with patch.object(survey_fetch, "_get_credentials", return_value=SimpleNamespace(token=secret)), patch("requests.post", **kwargs), contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                    result = survey_fetch.translate_text({"private_key": secret}, source)
                self.assertEqual(result, (source, None, False), "Cloud failure must be explicit")
        finally:
            logging.getLogger().removeHandler(handler)
        self.assertNotIn(source, output.getvalue())
        self.assertNotIn(secret, output.getvalue())


class SurveyTranslationTests(unittest.TestCase):
    def test_two_character_answer_is_translated_and_tagged(self):
        model = model_for(["卡顿"])
        cell = model["sections"][0]["rows"][0]["cells"][0]
        self.assertEqual(cell["value"], "Lagging")
        self.assertTrue(cell["translated"])
        self.assertEqual(cell.get("lang"), "zh-CN")
        self.assertIs(cell.get("translate_failed"), False)
        _, html = survey_render.render(model)
        self.assertIn("Translated from Chinese", html)
        self.assertNotIn("卡顿", html)

    def test_english_answer_is_unchanged_even_if_service_rephrases_it(self):
        source = "Keep my saved ports exactly as entered."
        model = model_for([source], translate_fn=lambda text: ("A rewritten answer", "en", True))
        cell = model["sections"][0]["rows"][0]["cells"][0]
        self.assertEqual(cell["value"], source)
        self.assertEqual(cell.get("lang"), "en")
        self.assertFalse(cell["translated"])
        self.assertIs(cell.get("translate_failed"), False)
        _, html = survey_render.render(model)
        self.assertIn(source, html)
        self.assertNotIn("Translated from", html)

    def test_empty_numeric_and_url_cells_do_not_acquire_failure_notes(self):
        def unavailable(text):
            raise RuntimeError("Translation service unavailable")
        model = model_for(["", "1234567", "5.5", "https://example.test/港口", "www.example.test"], translate_fn=unavailable)
        cells = [row["cells"][0] for row in model["sections"][0]["rows"]]
        self.assertEqual([cell["value"] for cell in cells], ["—", "1234567", "5.5", "https://example.test/港口", "www.example.test"])
        self.assertTrue(all(cell.get("translate_failed") is False for cell in cells))
        _, html = survey_render.render(model)
        self.assertNotIn("Translation unavailable", html)

    def test_missing_ship_vessel_name_stays_exact_while_details_translate(self):
        config = json.loads((ROOT / "data/survey_marine.json").read_text())
        row = [STAMP, "Le port manque", "1234567", "", "Tanker", "France", "", "卡顿"]
        model = survey_model.build_model(config, {"Add your ship ": [row]}, START, END, translated)
        cells = model["sections"][0]["rows"][0]["cells"]
        self.assertEqual(cells[0]["value"], "Le port manque")
        self.assertFalse(cells[0]["translated"])
        self.assertEqual(cells[-1]["value"], "Lagging")
        _, html = survey_render.render(model)
        self.assertIn("Le port manque", html)
        self.assertIn("Translated from Chinese", html)
        self.assertNotIn("卡顿", html)

    def test_cell_failure_shows_original_with_unavailable_note(self):
        model = model_for(["卡顿"], translate_fn=lambda text: (text, None, False))
        cell = model["sections"][0]["rows"][0]["cells"][0]
        self.assertIs(cell.get("translate_failed"), True)
        _, html = survey_render.render(model)
        self.assertIn("卡顿", html)
        self.assertIn("Translation unavailable", html)
        self.assertNotIn("Translated from", html)

    def test_translated_record_fields_and_tags_are_escaped(self):
        model = model_for([["Name", "卡顿", "More ports", "Value"]], columns=[
            {"col": 1, "header": "Name"}, {"col": 2, "header": "Detail <label>"},
            {"col": 3, "header": "Country"}, {"col": 4, "header": "Note"},
        ], translate_fn=lambda text: ("Lagging <script> & slow", "zh-CN", True) if text == "卡顿" else (text, "en", True))
        _, html = survey_render.render(model)
        self.assertIn("Lagging &lt;script&gt; &amp; slow", html)
        self.assertIn("Detail &lt;label&gt;", html)
        self.assertIn("Translated from Chinese", html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<label>", html)

    def test_distribution_merges_foreign_custom_options_with_english_twins(self):
        for mode in ("distribution", "summary"):
            with self.subTest(mode=mode):
                model = model_for(["Demasiado caro", "Too expensive", "Otro: avisos", "Other: alerts"], mode=mode, columns=[{
                    "col": 1, "header": "Reason", "color_map": {"Too expensive": "#c0392b"},
                }])
                key = "distributions" if mode == "distribution" else "summaries"
                options = model["sections"][0][key][0]["options"]
                self.assertEqual({option["value"]: option["count"] for option in options}, {"Too expensive": 2, "Other": 2})
                self.assertTrue(all(option["pct"] == 50 for option in options))
                _, html = survey_render.render(model)
                self.assertNotIn("Demasiado caro", html)
                self.assertNotIn("Otro: avisos", html)

    def test_distribution_failures_are_visible_standalone_and_inside_summary(self):
        for mode in ("distribution", "summary"):
            with self.subTest(mode=mode):
                model = model_for(["卡顿"], mode=mode, columns=[{
                    "col": 1, "header": "Reason", "color_map": {"Too expensive": "#c0392b"},
                }], translate_fn=lambda text: (text, None, False))
                key = "distributions" if mode == "distribution" else "summaries"
                option = model["sections"][0][key][0]["options"][0]
                self.assertIs(option.get("translate_failed"), True)
                _, html = survey_render.render(model)
                self.assertIn("卡顿", html)
                self.assertIn("Translation unavailable", html)

    def test_grouped_summary_keeps_short_answers_and_has_no_language_tag(self):
        model = model_for(["卡顿", "Lagging", "ok"], mode="summary")
        summary = model["sections"][0]["summaries"][0]
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["groups"], [{"text": "Lagging", "count": 2}])
        _, html = survey_render.render(model)
        self.assertIn("Lagging", html)
        self.assertNotIn("卡顿", html)
        self.assertNotIn("Translated from", html)

    def test_grouped_summary_preserves_failed_inputs_with_unavailable_note(self):
        model = model_for(["卡顿", "More ports"], mode="summary", translate_fn=lambda text: (text, None, False) if text == "卡顿" else translated(text))
        groups = model["sections"][0]["summaries"][0]["groups"]
        failed = [group for group in groups if group.get("translate_failed")]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["text"], "卡顿")
        self.assertEqual(sum(group["count"] for group in groups), 2)
        _, html = survey_render.render(model)
        self.assertIn("Translation unavailable", html)
        self.assertIn("More ports", html)
        self.assertNotIn("Translated from", html)

    def test_geo_main_translates_two_character_detail_and_open_feedback(self):
        responses = [{"submitted_at": STAMP, "answers": [
            {"question_index": 0, "question_type": "single_choice", "answer": "Exporting video"},
            {"question_index": 6, "question_type": "multiple_choice", "answer": '["卡顿"]'},
            {"question_index": 7, "question_type": "open", "answer": "卡顿"},
        ]}]
        previews = []
        output = io.StringIO()
        environment = {
            "GOOGLE_SA_KEY": base64.b64encode(b"{}").decode(), "GOOGLE_API_KEY": "",
            "POSTHOG_GEO_API_KEY": "private-posthog-key", "GITHUB_ACTIONS": "false",
        }
        with patch.dict(os.environ, environment), patch.object(survey_main, "fetch_responses", return_value=responses), patch.object(survey_main, "translate_text", side_effect=lambda sa_info, text: translated(text)), patch.object(survey_main, "write_preview", side_effect=lambda digest, edition, title, html: previews.append(html)), patch.object(survey_main, "send_digest", side_effect=AssertionError("Preview must not send email")), contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            survey_main.main(["--digest", "survey_geo", "--edition", "pt", "--report-date", "2026-11-05", "--dry-run"])
        self.assertEqual(len(previews), 1)
        self.assertIn("Open Feedback", previews[0])
        self.assertIn("Lagging", previews[0])
        self.assertNotIn("卡顿", previews[0])
        self.assertNotIn("卡顿", output.getvalue())
        self.assertNotIn("private-posthog-key", output.getvalue())


if __name__ == "__main__":
    unittest.main()
