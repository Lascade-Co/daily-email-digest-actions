"""Fixed translation regressions; never print these inputs.

The Portuguese and romanized Hindi bodies are from the approved handoff.
Russian, Indonesian, and English are synthetic examples: the handoff did not
include the exact Russian/Indonesian November 4 review titles or bodies.
"""
from datetime import datetime, timezone


REVIEW_CASES = (
    {"language": "ru", "title": "Карта не работает", "body": "Карта не загружается после обновления.",
     "title_en": "The map does not work", "body_en": "The map does not load after the update."},
    {"language": "id", "title": "", "body": "Peta tidak bisa dimuat setelah pembaruan.",
     "title_en": "", "body_en": "The map cannot be loaded after the update."},
    {"language": "pt", "title": "", "body": "até é bom",
     "title_en": "", "body_en": "It is actually good."},
    {"language": "hi", "title": "", "body": "natak kar raha hai",
     "title_en": "", "body_en": "It is acting up."},
    {"language": "en", "title": "Saved routes", "body": "Please keep my saved routes after an update.",
     "title_en": "Saved routes", "body_en": "Please keep my saved routes after an update."},
)
CHINESE_CASE = {"language": "zh", "title": "", "body": "卡顿",
                "title_en": "", "body_en": "Lagging"}
LIVE_CASES = REVIEW_CASES + (CHINESE_CASE,)
MOMENT = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)


def review_inputs(cases=REVIEW_CASES):
    return [{"title": case["title"], "body": case["body"], "rating": 2,
             "date": MOMENT, "store": "appstore", "author": "Fixture reviewer"}
            for case in cases]
