"""Real-check safety contracts with network boundaries replaced offline."""
import base64
import contextlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import live_translation_check as live
from translation_cases import LIVE_CASES, REVIEW_CASES
from scripts.reviews import reviews_model
from scripts.survey import survey_fetch


class LiveTranslationCheckTests(unittest.TestCase):
    def _response(self):
        items = [{"id": i, "language": c["language"], "title_en": c["title_en"],
                  "body_en": c["body_en"]} for i, c in enumerate(LIVE_CASES)]
        return io.BytesIO(json.dumps({"candidates": [{"content": {
            "parts": [{"text": json.dumps(items)}]}}]}).encode())

    def _run(self, *, cloud_fails=False, gemini_fails=False):
        values = {c[field]: (c[field + "_en"], c["language"])
                  for c in LIVE_CASES for field in ("title", "body") if c[field]}
        counts = {"gemini": 0, "cloud": 0}

        def gemini(*args, **kwargs):
            counts["gemini"] += 1
            if gemini_fails:
                raise RuntimeError("fixture-private-key " + REVIEW_CASES[0]["body"])
            return self._response()

        def cloud(url, *, json, **kwargs):
            counts["cloud"] += 1
            if cloud_fails:
                raise RuntimeError("fixture-private-key " + REVIEW_CASES[0]["body"])
            text, lang = values[json["q"]]
            return SimpleNamespace(status_code=200, json=lambda: {"data": {"translations": [
                {"translatedText": text, "detectedSourceLanguage": lang}]}})

        output = io.StringIO()
        environment = {"GOOGLE_API_KEY": "fixture-private-key", "GOOGLE_SA_KEY":
                       base64.b64encode(b'{"private_key":"fixture-private-key"}').decode()}
        with (patch.dict(os.environ, environment),
              patch.object(reviews_model.urllib.request, "urlopen", side_effect=gemini),
              patch.object(survey_fetch, "_get_credentials", return_value=SimpleNamespace(token="fixture-token")),
              patch("requests.post", side_effect=cloud),
              contextlib.redirect_stdout(output), contextlib.redirect_stderr(output)):
            status = live.main()
        return status, output.getvalue(), counts

    def test_real_model_checks_both_engines_and_two_character_survey_without_delivery(self):
        status, output, counts = self._run()
        self.assertEqual(status, 0)
        self.assertEqual(counts["gemini"], 1)
        self.assertGreater(counts["cloud"], 0)
        self.assertEqual(len(output.splitlines()), 14)
        for line in output.splitlines():
            self.assertRegex(line, r"^(reviews (gemini|cloud) case=[1-6]|survey case=1): PASS$")
        for case in LIVE_CASES:
            self.assertNotIn(case["body"], output)
        self.assertNotIn("fixture-private-key", output)

    def test_failed_cloud_path_fails_check_without_leaking_exception_details(self):
        status, output, _ = self._run(cloud_fails=True)
        self.assertEqual(status, 1)
        self.assertIn("reviews cloud case=1: FAIL", output)
        self.assertIn("survey case=1: FAIL", output)
        self.assertNotIn("fixture-private-key", output)
        self.assertNotIn(REVIEW_CASES[0]["body"], output)
        self.assertNotIn("Traceback", output)

    def test_gemini_failure_cannot_pass_by_silently_using_cloud(self):
        status, output, counts = self._run(gemini_fails=True)
        self.assertEqual(status, 1)
        self.assertEqual(counts["gemini"], 2)
        self.assertIn("reviews gemini case=1: FAIL", output)
        self.assertIn("reviews cloud case=1: PASS", output)
        self.assertNotIn("fixture-private-key", output)

    def test_missing_or_invalid_credentials_fail_with_only_fixed_text(self):
        for sa_key in ("", "fixture-private-key"):
            with self.subTest(valid=bool(sa_key)), patch.dict(os.environ, {
                    "GOOGLE_API_KEY": "fixture-private-key", "GOOGLE_SA_KEY": sa_key}), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(live.main(), 1)
            self.assertEqual(output.getvalue(), "translation setup: FAIL\n")

    def test_case_checks_reject_unchanged_foreign_text_missing_title_and_changed_english(self):
        foreign = REVIEW_CASES[0]
        valid = {"language": "ru", "is_non_english": True,
                 "translated_title": foreign["title_en"], "translated_body": foreign["body_en"]}
        self.assertTrue(live.review_passed(foreign, valid))
        for changes in ({"translated_body": foreign["body"]}, {"translated_title": ""},
                        {"translated_body": foreign["body"] + "!"}, {"translate_failed": True},
                        {"language": "en"}):
            candidate = {**valid, **changes}
            self.assertFalse(live.review_passed(foreign, candidate))
        english = REVIEW_CASES[4]
        valid = {"language": "en", "is_non_english": False,
                 "translated_title": english["title"], "translated_body": english["body"]}
        self.assertTrue(live.review_passed(english, valid))
        self.assertFalse(live.review_passed(english, {**valid, "translated_body": "Rewritten"}))


class LiveWorkflowTests(unittest.TestCase):
    def test_manual_workflow_has_full_checkout_and_only_translation_secrets(self):
        import yaml
        path = Path(__file__).resolve().parents[1] / ".github/workflows/live-translation-check.yml"
        self.assertTrue(path.exists(), "Standalone live check workflow is missing")
        workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
        self.assertEqual(set(workflow["on"]), {"workflow_dispatch"})
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertEqual(set(workflow["jobs"]), {"check"})
        job = workflow["jobs"]["check"]
        self.assertNotIn("uses", job)
        checkout = next(step for step in job["steps"] if "actions/checkout@" in step.get("uses", ""))
        self.assertNotIn("sparse-checkout", checkout.get("with", {}))
        check = next(step for step in job["steps"] if step.get("run") == "python3 tests/live_translation_check.py")
        self.assertEqual(check["env"], {"GOOGLE_API_KEY": "${{ secrets.GOOGLE_API_KEY }}",
                                       "GOOGLE_SA_KEY": "${{ secrets.GOOGLE_SA_KEY }}"})
        self.assertNotIn("env", workflow)
        self.assertNotIn("env", job)
        for step in job["steps"]:
            self.assertNotIn("settings", step.get("run", ""))
            self.assertNotIn("delivery", step.get("run", ""))
            self.assertNotIn("upload-artifact", step.get("uses", ""))


if __name__ == "__main__":
    unittest.main()
