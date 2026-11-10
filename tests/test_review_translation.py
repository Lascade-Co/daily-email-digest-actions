"""Offline review translation, fallback, and safe rendering contracts."""
import base64
import contextlib
from datetime import datetime, timezone
import io
import json
import os
import unittest
from unittest.mock import patch

from scripts.reviews import reviews_main, reviews_model, reviews_render
from scripts.survey import survey_fetch
from test_strict_render import Document


SHORT = "até é bom"
ROMANIZED = "natak kar raha hai"
SPANISH = "La aplicación pierde mi <ruta> & mis lugares guardados."
SPANISH_TITLE = "Ruta perdida"
ENGLISH = "  Please keep the map visible when I open settings.  "
POSITIVE = "La aplicación funciona muy bien y me encanta."
MOMENT = datetime(2026, 11, 4, 20, tzinfo=timezone.utc)
TRANSLATIONS = [
    {"id": 3, "language": "es", "title_en": "Lost route",
     "body_en": "The app loses my <route> & my saved places."},
    {"id": 2, "language": "en", "title_en": "A rewritten English title",
     "body_en": "A rewritten English review that must be ignored."},
    {"id": 1, "language": "hi", "title_en": "", "body_en": "It is acting up."},
    {"id": 0, "language": "pt", "title_en": "", "body_en": "It is actually good."},
]


def review(body, title="", rating=2, store="appstore"):
    return {"body": body, "title": title, "rating": rating, "date": MOMENT,
            "store": store, "author": "Fixture author"}


def gemini_response(translations):
    return io.BytesIO(json.dumps({
        "candidates": [{
            "content": {"parts": [{"text": json.dumps(translations)}], "role": "model"},
            "finishReason": "STOP", "index": 0,
        }],
    }).encode())


class ReviewTranslationTests(unittest.TestCase):
    def _build(self, reviews=None, **kwargs):
        if reviews is None:
            reviews = [review(SHORT), review(ROMANIZED), review(ENGLISH, "Keep my map", rating=3),
                       review(SPANISH, SPANISH_TITLE), review(POSITIVE, rating=5)]
        return reviews_model.build_model(
            [{"name": "Fixture app"}], {"Fixture app": {"appstore": reviews, "playstore": []}},
            MOMENT, MOMENT, **kwargs,
        )

    def _cards(self, model):
        _, html = reviews_render.render(model)
        return Document(html).root.find("td", "card-bg"), html

    def _preview(self, cloud_translate, key="fixture-gemini-key"):
        """Exercise the CLI/model/render path with external boundaries replaced."""
        captured = {}
        appstore = {
            "6560109315": [review(POSITIVE, rating=5)],
            "6736476968": [review(SPANISH, SPANISH_TITLE)],
        }
        playstore = {
            "com.lascade.marinetracker": [review(SHORT, store="playstore")],
            "com.lascade.geoanimator": [review(ENGLISH, store="playstore")],
            "com.travelanimator.routemap": [review(ROMANIZED, store="playstore")],
        }

        def capture_preview(digest, edition, subject, html):
            captured.update(html=html, subject=subject)

        environment = {
            "ASC_KEY_ID": "fixture-asc-key", "ASC_ISSUER_ID": "fixture-issuer",
            "ASC_PRIVATE_KEY": "fixture-private-key",
            "GOOGLE_SA_KEY": base64.b64encode(b'{"type":"service_account","client_email":"fixture@example.test"}').decode(),
            "GOOGLE_API_KEY": key, "GITHUB_ACTIONS": "false",
        }
        output = io.StringIO()
        with (
            patch.dict(os.environ, environment),
            patch.object(reviews_main, "fetch_appstore_reviews", side_effect=lambda app_id, *a, **kw: (appstore.get(app_id, []), "ok")),
            patch.object(reviews_main, "fetch_playstore_reviews", side_effect=lambda package, *a, **kw: (playstore.get(package, []), "ok")),
            patch.object(survey_fetch, "translate_text", side_effect=cloud_translate),
            patch.object(reviews_main, "write_preview", side_effect=capture_preview),
            patch.object(reviews_main, "send_digest", side_effect=AssertionError("dry run must not send")),
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(output),
        ):
            reviews_main.main(["--edition", "pt", "--report-date", "2026-11-04", "--dry-run"])
        return captured, output.getvalue()

    def test_short_and_romanized_reviews_and_titles_are_translated_in_one_batch(self):
        requests = []

        def respond(request, timeout):
            requests.append((request, timeout))
            return gemini_response(TRANSLATIONS)

        with patch("urllib.request.urlopen", side_effect=respond):
            model = self._build(gemini_key="fixture-gemini-key")
        cards, html = self._cards(model)
        self.assertEqual([card.find("p", "text-main")[0].text for card in cards], [
            "It is actually good.", "It is acting up.", ENGLISH,
            "The app loses my <route> & my saved places.",
        ])
        self.assertIn("Lost route", cards[3].find("h4")[0].text)
        self.assertNotIn(SPANISH_TITLE, html)
        for original in (SHORT, ROMANIZED, SPANISH, POSITIVE):
            self.assertNotIn(original, html)
        self.assertEqual([badge.text for card in cards for badge in card.find("span", "callout-info-bg")],
                         ["Translated from Portuguese", "Translated from Hindi", "Translated from Spanish"])
        self.assertNotIn("Non-English", html)
        self.assertNotIn("<route>", html)
        self.assertNotIn("<ruta>", html)
        self.assertEqual(len(requests), 1)
        request, timeout = requests[0]
        self.assertEqual(timeout, 30)
        payload = json.loads(request.data)
        self.assertEqual(payload["generationConfig"]["responseMimeType"], "application/json")
        sent = json.loads(payload["contents"][0]["parts"][0]["text"].split("Reviews:\n", 1)[1])
        self.assertEqual(sent, [
            {"id": 0, "title": "", "body": SHORT},
            {"id": 1, "title": "", "body": ROMANIZED},
            {"id": 2, "title": "Keep my map", "body": ENGLISH},
            {"id": 3, "title": SPANISH_TITLE, "body": SPANISH},
        ])
        translated = model["apps"][0]["appstore_reviews"]
        self.assertEqual([item["language"] for item in translated], ["pt", "hi", "en", "es"])
        self.assertEqual([item["is_non_english"] for item in translated], [True, True, False, True])

    def test_english_text_stays_exact_even_if_model_rewrites_it(self):
        response = [{"id": 0, "language": "en", "title_en": "Changed title", "body_en": "Changed body"}]
        with patch("urllib.request.urlopen", side_effect=lambda *a, **kw: gemini_response(response)):
            model = self._build([review(ENGLISH, "  Keep my map  ")], gemini_key="fixture-key")
        card = self._cards(model)[0][0]
        self.assertEqual(card.find("p", "text-main")[0].text, ENGLISH)
        self.assertTrue(card.find("h4")[0].text.endswith("  Keep my map  "))
        self.assertFalse(card.find("span", "callout-info-bg"))
        self.assertFalse(model["apps"][0]["appstore_reviews"][0]["is_non_english"])

    def test_failed_first_attempt_retries_with_a_longer_timeout(self):
        timeouts = []

        def respond(request, timeout):
            timeouts.append(timeout)
            if len(timeouts) == 1:
                raise TimeoutError("fixture-private-exception")
            return gemini_response(TRANSLATIONS)

        with patch("urllib.request.urlopen", side_effect=respond), self.assertLogs(reviews_model.log, level="WARNING"):
            model = self._build(gemini_key="fixture-key")
        self.assertEqual(timeouts, [30, 60])
        self.assertIn("It is acting up.", self._cards(model)[1])

    def test_bad_translation_batches_fail_closed_without_content_in_logs(self):
        valid = {"id": 0, "language": "es", "title_en": "Lost route", "body_en": "The route is lost."}
        second = {"id": 1, "language": "pt", "title_en": "", "body_en": "It is actually good."}
        malformed = [
            {"body_en": "Wrong outer shape"}, [valid], [valid, valid],
            [valid, {**second, "id": 3}], [valid, {**second, "id": True}],
            [valid, {**second, "body_en": "  "}], [valid, {**second, "body_en": None}],
            [{**valid, "title_en": ""}, second], [{**valid, "title_en": None}, second],
            [valid, {**second, "language": "Hindi"}], [valid, {**second, "language": ""}],
            [valid, {**second, "language": None}],
        ]
        for case, response in enumerate(malformed):
            with self.subTest(case=case), \
                    patch("urllib.request.urlopen", side_effect=lambda *a, **kw: gemini_response(response)), \
                    self.assertLogs(reviews_model.log, level="WARNING") as logs:
                model = self._build([review(SPANISH, SPANISH_TITLE), review(SHORT)], gemini_key="fixture-key")
                cards, html = self._cards(model)
                self.assertEqual([card.find("p", "text-main")[0].text for card in cards], [SPANISH, SHORT])
                self.assertEqual(html.count(">Translation unavailable</span>"), 2)
                self.assertNotIn("Translated from", html)
                self.assertNotIn("Non-English", html)
            for sensitive in (SPANISH, SPANISH_TITLE, SHORT, "fixture-key"):
                self.assertNotIn(sensitive, "\n".join(logs.output))

    def test_empty_low_rating_batch_never_contacts_translation_service(self):
        def unexpected(*args, **kwargs):
            self.fail("Empty batch contacted translation service")

        with patch("urllib.request.urlopen", side_effect=unexpected):
            model = self._build([review(POSITIVE, rating=5)], gemini_key="fixture-key")
        self.assertEqual(model["grand_total"], 0)

    def test_two_gemini_failures_use_cloud_for_each_review_title_and_body(self):
        cloud_inputs, attempts = [], []

        def cloud(sa_info, text):
            self.assertEqual(sa_info, {"type": "service_account", "client_email": "fixture@example.test"})
            cloud_inputs.append(text)
            return {
                SHORT: ("It is actually good.", "pt", True),
                SPANISH_TITLE: ("Lost route", "es", True),
                SPANISH: ("The app loses my <route> & my saved places.", "es", True),
                ENGLISH: ("A rewrite that must be ignored.", "en", True),
                ROMANIZED: ("It is acting up.", "hi", True),
            }[text]

        def fail(request, timeout):
            attempts.append(timeout)
            raise TimeoutError(SPANISH + " fixture-gemini-key")

        with patch("urllib.request.urlopen", side_effect=fail), self.assertLogs(reviews_model.log, level="WARNING"):
            preview, _ = self._preview(cloud)
        cards = Document(preview["html"]).root.find("td", "card-bg")
        self.assertEqual([card.find("p", "text-main")[0].text for card in cards], [
            "It is actually good.", "The app loses my <route> & my saved places.", ENGLISH, "It is acting up.",
        ])
        self.assertIn("Lost route", cards[1].find("h4")[0].text)
        self.assertEqual(attempts, [30, 60])
        self.assertCountEqual(cloud_inputs, [SHORT, SPANISH_TITLE, SPANISH, ENGLISH, ROMANIZED])
        self.assertEqual(preview["html"].count("Translated from"), 3)

    def test_cloud_failure_is_per_review_and_marks_originals_without_false_language(self):
        def cloud(sa_info, text):
            if text == SHORT:
                return text, "", False
            return {
                SPANISH_TITLE: ("Lost route", "es", True),
                SPANISH: ("The app loses my <route> & my saved places.", "es", True),
                ENGLISH: (ENGLISH, "en", True),
                ROMANIZED: ("It is acting up.", "hi", True),
            }[text]

        with patch("urllib.request.urlopen", side_effect=TimeoutError), self.assertLogs(reviews_model.log, level="WARNING"):
            preview, _ = self._preview(cloud)
        cards = Document(preview["html"]).root.find("td", "card-bg")
        self.assertEqual([card.find("p", "text-main")[0].text for card in cards], [
            SHORT, "The app loses my <route> & my saved places.", ENGLISH, "It is acting up.",
        ])
        self.assertEqual(preview["html"].count(">Translation unavailable</span>"), 1)
        self.assertNotIn("Non-English", preview["html"])

    def test_both_services_fail_without_logging_feedback_titles_recipients_or_keys(self):
        private = SPANISH + SPANISH_TITLE + " fixture-gemini-key fixture@example.test fixture-subject"

        def cloud(sa_info, text):
            raise RuntimeError(private)

        with patch("urllib.request.urlopen", side_effect=RuntimeError(private)), \
                self.assertLogs(reviews_model.log, level="WARNING") as logs:
            preview, output = self._preview(cloud)
        cards = Document(preview["html"]).root.find("td", "card-bg")
        self.assertEqual([card.find("p", "text-main")[0].text for card in cards],
                         [SHORT, SPANISH, ENGLISH, ROMANIZED])
        self.assertEqual(preview["html"].count(">Translation unavailable</span>"), 4)
        self.assertNotIn("Non-English", preview["html"])
        for sensitive in (SHORT, ROMANIZED, SPANISH, SPANISH_TITLE, ENGLISH, preview["subject"],
                          "fixture-gemini-key", "fixture@example.test", "fixture-subject"):
            self.assertNotIn(sensitive, output + "\n".join(logs.output))

    def test_missing_gemini_key_uses_cloud_without_gemini_request(self):
        requests = []

        def unexpected(*args, **kwargs):
            requests.append(args)
            raise AssertionError("Missing key contacted Gemini")

        def cloud(sa_info, text):
            return "English fixture text", "es", True

        with patch("urllib.request.urlopen", side_effect=unexpected):
            preview, _ = self._preview(cloud, key="")
        self.assertEqual(requests, [])
        self.assertEqual(preview["html"].count(">English fixture text</p>"), 4)

    def test_translation_badges_name_source_languages(self):
        for code, name in {"ru": "Russian", "id": "Indonesian", "pt": "Portuguese", "hi": "Hindi",
                           "zh": "Chinese", "zh-cn": "Chinese", "zh-tw": "Chinese", "nl": "Dutch"}.items():
            with self.subTest(language=code):
                html = reviews_render._review_card({
                    "rating": 2, "body": "Original fixture text", "translated_body": "English fixture text",
                    "is_non_english": True, "language": code,
                })
                self.assertIn(f"Translated from {name}", [badge.text for badge in Document(html).root.find("span")])


if __name__ == "__main__":
    unittest.main()
