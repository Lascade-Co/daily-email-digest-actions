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
from test_strict_render import Document


SPANISH = "La aplicación pierde mi <ruta> & mis lugares guardados."
FRENCH = "Je ne retrouve pas les <ports> après la mise à jour."
ENGLISH = "Please keep the map visible when I open settings."
POSITIVE = "La aplicación funciona muy bien y me encanta."
TRANSLATIONS = [
    {"id": 1, "translation": "I cannot find the <ports> after the update."},
    {"id": 0, "translation": "The app loses my <route> & my saved places."},
]


def gemini_response(translations):
    return io.BytesIO(json.dumps({
        "candidates": [{
            "content": {"parts": [{"text": json.dumps(translations)}], "role": "model"},
            "finishReason": "STOP",
            "index": 0,
        }],
    }).encode())


class ReviewTranslationTests(unittest.TestCase):
    def _preview(self, key="fixture-gemini-key"):
        """Run the real CLI/model/render path with only external boundaries replaced."""
        moment = datetime(2026, 10, 20, 20, tzinfo=timezone.utc)
        captured = {}

        def review(body, rating=2, store="appstore"):
            return {"body": body, "rating": rating, "date": moment, "store": store,
                    "title": "Fixture review", "author": "Fixture author"}

        appstore = {
            "6560109315": [review(POSITIVE, rating=5)],
            "6736476968": [review(FRENCH)],
        }
        playstore = {
            "com.lascade.marinetracker": [review(SPANISH, store="playstore")],
            "com.lascade.geoanimator": [review(ENGLISH, store="playstore")],
        }

        def capture_preview(digest, edition, subject, html):
            captured["html"] = html

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
            patch.object(reviews_model, "detect_language", side_effect=lambda text: {SPANISH: "es", FRENCH: "fr"}.get(text, "en")),
            patch.object(reviews_main, "write_preview", side_effect=capture_preview),
            patch.object(reviews_main, "send_digest", side_effect=AssertionError("dry run must not send")),
            contextlib.redirect_stdout(output),
        ):
            reviews_main.main(["--edition", "pt", "--report-date", "2026-10-21", "--dry-run"])
        return captured["html"], output.getvalue()

    def test_batches_reviews_and_renders_english_with_original_caption(self):
        requests = []

        def respond(request, timeout):
            requests.append((request, timeout))
            return gemini_response(TRANSLATIONS)

        with patch("urllib.request.urlopen", side_effect=respond):
            html, output = self._preview()
        cards = Document(html).root.find("td", "card-bg")
        self.assertEqual([card.find("p", "text-main")[0].text for card in cards], [
            "The app loses my <route> & my saved places.",
            "I cannot find the <ports> after the update.",
            ENGLISH,
        ])
        for card, original, language in zip(cards, [SPANISH, FRENCH], ["Spanish", "French"]):
            caption = card.find("p", "text-muted")[0]
            self.assertEqual(caption.text, original)
            self.assertIn("font-size:13px;", caption.attrs["style"])
            self.assertIn("color:#666666;", caption.attrs["style"])
            badge = card.find("span", "callout-info-bg")[0]
            self.assertEqual(badge.text, f"Translated · {language}")
            self.assertIn("background-color:#eef5fb;", badge.attrs["style"])
        self.assertNotIn("Non-English", html)
        self.assertNotIn("<route>", html)
        self.assertNotIn("<ports>", html)
        self.assertNotIn("<ruta>", html)
        self.assertEqual(len(requests), 1)
        request, timeout = requests[0]
        self.assertEqual(timeout, 15)
        self.assertEqual(request.full_url, "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key=fixture-gemini-key")
        payload = json.loads(request.data)
        self.assertEqual(payload["generationConfig"]["responseMimeType"], "application/json")
        self.assertNotIn("temperature", payload["generationConfig"])
        prompt = payload["contents"][0]["parts"][0]["text"]
        self.assertIn(SPANISH, prompt)
        self.assertIn(FRENCH, prompt)
        self.assertNotIn(ENGLISH, prompt)
        self.assertNotIn(POSITIVE, prompt)
        for sensitive in (SPANISH, FRENCH, "fixture-gemini-key"):
            self.assertNotIn(sensitive, output)

    def test_translation_failure_preserves_original_without_logging_review_or_key(self):
        with (
            patch("urllib.request.urlopen", side_effect=RuntimeError(SPANISH + " fixture-gemini-key")),
            self.assertLogs("scripts.reviews.reviews_model", level="WARNING") as logs,
        ):
            html, output = self._preview()
        cards = Document(html).root.find("td", "card-bg")
        self.assertEqual([card.find("p", "text-main")[0].text for card in cards], [SPANISH, FRENCH, ENGLISH])
        self.assertEqual(html.count(">Non-English</span>"), 2)
        self.assertNotIn("Translated ·", html)
        for sensitive in (SPANISH, FRENCH, "fixture-gemini-key"):
            self.assertNotIn(sensitive, "\n".join(logs.output) + output)

    def test_missing_key_keeps_muted_non_english_badge_without_network(self):
        requests = []

        def respond(*args, **kwargs):
            requests.append(args)
            return gemini_response(TRANSLATIONS)

        with patch("urllib.request.urlopen", side_effect=respond):
            html, _ = self._preview(key="")
        self.assertEqual(requests, [])
        cards = Document(html).root.find("td", "card-bg")
        self.assertEqual([card.find("p", "text-main")[0].text for card in cards], [SPANISH, FRENCH, ENGLISH])
        for card in cards[:2]:
            self.assertEqual(card.find("span", "text-muted")[0].text, "Non-English")
        self.assertNotIn("Translated ·", html)

    def test_malformed_or_partial_translation_response_falls_back_as_a_batch(self):
        malformed = [
            {"translation": "Wrong outer shape"},
            [{"id": 0, "translation": "Only one response"}],
            [{"id": 0, "translation": "First"}, {"id": 0, "translation": "Duplicate"}],
            [{"id": 0, "translation": "First"}, {"id": 1, "translation": "  "}],
            [{"id": 0, "translation": "First"}, {"id": 1, "translation": None}],
            [{"id": 0, "translation": "First"}, {"id": 3, "translation": "Unknown ID"}],
            [{"id": 0, "translation": "First"}, {"id": True, "translation": "Invalid ID"}],
        ]
        for response in malformed:
            with self.subTest(response=response):
                with patch("urllib.request.urlopen", side_effect=lambda *a, **kw: gemini_response(response)), self.assertLogs("scripts.reviews.reviews_model", level="WARNING"):
                    html, _ = self._preview()
                cards = Document(html).root.find("td", "card-bg")
                self.assertEqual([card.find("p", "text-main")[0].text for card in cards], [SPANISH, FRENCH, ENGLISH])
                self.assertNotIn("Translated ·", html)

    def test_translation_badge_names_detected_languages(self):
        names = {
            "es": "Spanish", "pt": "Portuguese", "fr": "French", "de": "German",
            "it": "Italian", "id": "Indonesian", "hi": "Hindi", "ru": "Russian",
            "tr": "Turkish", "ar": "Arabic", "ja": "Japanese", "ko": "Korean",
            "zh-cn": "Chinese", "zh-tw": "Chinese", "vi": "Vietnamese", "nl": "NL",
        }
        for code, name in names.items():
            with self.subTest(language=code):
                html = reviews_render._review_card({
                    "rating": 2, "body": "Original fixture text", "translated_body": "English fixture text",
                    "is_non_english": True, "language": code,
                })
                self.assertIn(f"Translated · {name}", [badge.text for badge in Document(html).root.find("span")])


if __name__ == "__main__":
    unittest.main()
