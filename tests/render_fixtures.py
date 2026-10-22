"""Offline, synthetic renderer fixtures and a local HTML preview writer.

Run from the repository root: python3 tests/render_fixtures.py <output-directory>
Mobile acceptance fixtures: python3 tests/render_fixtures.py --mobile <output-directory>
"""
from copy import deepcopy
from importlib import import_module
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def fixture_models():
    """Return independent models containing no customer or network data."""
    revenue = {
        "today_total": 412.0, "today_count": 3,
        "today_refund_total": 29.0, "today_refund_count": 1,
        "packs": [
            {"amount": "99.00", "count": 2, "total": 198.0},
            {"amount": "214.00", "count": 1, "total": 214.0},
        ],
        "month_total": 4120.0, "month_count": 30,
        "month_refund_total": 290.0, "month_refund_count": 10,
        "month_net": 3830.0, "month_label": "1–21 Oct 2026",
        "date_str": "Wednesday, 21 October 2026",
        "cutoff_str": "20 Oct 5:00 AM PDT",
    }
    reviews = {
        "grand_total": 2, "total_fetched": 5, "max_rating": 3,
        "overall_avg": 2.0,
        "date_str": "Wednesday, 21 October 2026",
        "since_str": "20 Oct 5:00 AM PDT",
        "app_names": ["MarineRadar", "Smart Ruler"],
        "apps": [
            {
                "name": "MarineRadar", "count": 2, "avg_rating": 2.0,
                "appstore_reviews": [{
                    "rating": 1, "title": "Route <script> & chart",
                    "body": "Please retain <waypoints> & route history.",
                    "store": "appstore", "country": "United States",
                    "author": "Fixture reviewer", "version": "2.4.0",
                    "is_non_english": False,
                }],
                "playstore_reviews": [{
                    "rating": 3, "title": "More map detail",
                    "body": "The map could use more harbor labels.",
                    "store": "playstore", "device": "Fixture phone",
                    "os_version": "Android 16", "author": "Sample reviewer",
                    "version": "2.4.1", "is_non_english": True,
                }],
            },
            {
                "name": "Smart Ruler", "count": 0, "avg_rating": 0.0,
                "appstore_reviews": [], "playstore_reviews": [],
            },
        ],
    }
    survey = {
        "product_name": "MarineRadar", "email_title": "MarineRadar Surveys",
        "total": 8, "survey_count": 3, "free_count": 1, "pro_count": 2,
        "date_str": "Wednesday, 21 October 2026",
        "cutoff_str": "20 Oct 5:00 AM PDT",
        "sheet_url": "https://docs.google.com/spreadsheets/d/fixture?view=all&edition=pt",
        "sections": [
            {
                "label": "Map survey", "subtitle": "Recent feedback", "count": 2,
                "render": "table", "has_status": True,
                "columns": ["Feedback", "Score"],
                "rows": [
                    {"status_label": "Pro", "status_color": "#5a5aad", "cells": [
                        {"value": "More <routes> & ports", "color": "#222", "bold": False},
                        {"value": "4/5", "color": "#2a8c4a", "bold": True},
                    ]},
                    {"status_label": "Free", "status_color": "#888", "cells": [
                        {"value": "Offline maps", "color": "#222", "bold": False},
                        {"value": "3/5", "color": "#c9922a", "bold": True},
                    ]},
                ],
            },
            {
                "label": "Feature survey", "subtitle": "Selected features", "count": 3,
                "render": "distribution", "has_status": False,
                "distributions": [{"header": "Most useful", "total": 3, "options": [
                    {"value": "Live map", "count": 2, "pct": 66.7, "color": "#4a90d9"},
                    {"value": "Port alerts", "count": 1, "pct": 33.3, "color": "#e67e22"},
                ]}],
            },
            {
                "label": "Experience survey", "subtitle": "Response themes", "count": 3,
                "render": "summary", "has_status": True,
                "summaries": [
                    {"header": "Satisfaction", "type": "score", "avg": 4.3, "total": 3},
                    {"header": "Plan", "type": "distribution", "total": 3, "options": [
                        {"value": "Pro", "count": 2, "pct": 66.7, "color": "#2a8c4a"},
                        {"value": "Free", "count": 1, "pct": 33.3, "color": "#c9922a"},
                    ]},
                    {"header": "Requests", "type": "grouped", "total": 3, "groups": [
                        {"text": "Add <harbor> alerts & weather", "count": 2},
                        {"text": "Keep recent searches", "count": 1},
                    ]},
                    {"header": "Other comments", "type": "grouped", "total": 0, "groups": []},
                ],
            },
        ],
    }
    survey_measure = deepcopy(survey)
    survey_measure.update(product_name="Smart Ruler", email_title="Smart Ruler Surveys")
    conversion = {
        "date_str": "Wednesday, 21 October 2026",
        "app_names": ["MarineRadar", "Smart Ruler", "GeoAnimator"],
        "apps": [
            {
                "name": "MarineRadar", "overall_rate": 3.2,
                "total_paid": 32, "total_installs": 1000, "has_data": True,
                "cohorts": [
                    {"date": "2026-10-20", "installs": 500, "paid": 15, "rate": 3.0},
                    {"date": "2026-10-19", "installs": 500, "paid": 17, "rate": 3.4},
                ],
            },
            {
                "name": "Smart Ruler", "overall_rate": 5.5,
                "total_paid": 55, "total_installs": 1000, "has_data": True,
                "cohorts": [
                    {"date": "2026-10-20", "installs": 500, "paid": 25, "rate": 5.0},
                    {"date": "2026-10-19", "installs": 500, "paid": 30, "rate": 6.0},
                ],
            },
            {
                "name": "GeoAnimator", "overall_rate": 0.0,
                "total_paid": 0, "total_installs": 0, "has_data": False, "cohorts": [],
            },
        ],
    }
    return {"revenue": revenue, "reviews": reviews, "survey_marine": survey,
            "survey_measure": survey_measure, "conversion": conversion}


def render_fixture(digest, model):
    module = "survey" if digest.startswith("survey_") else digest
    renderer = import_module(f"scripts.{module}.{module}_render")
    return renderer.render(model)


def mobile_fixture_models():
    """Include translated Spanish feedback and a five-column ship submission."""
    models = fixture_models()
    reviews = models["reviews"]
    reviews["app_names"][0] = "GeoAnimator"
    reviews["apps"][0]["name"] = "GeoAnimator"
    review = reviews["apps"][0]["playstore_reviews"][0]
    review.update(
        title="",
        body="El mapa necesita más etiquetas de puertos y rutas guardadas.",
        language="es",
        translated_body="The map needs more harbor labels and saved routes.",
    )
    survey = models["survey_marine"]
    survey["total"] += 2
    survey["survey_count"] += 1
    survey["sections"].append({
        "label": "Missing Ships", "subtitle": "Submissions", "count": 2,
        "render": "table", "has_status": False,
        "columns": ["Vessel", "IMO", "Type", "Country", "Details"],
        "rows": [
            {"cells": [{"value": value} for value in [
                "Britannic", "1234567", "Passenger vessel", "United Kingdom",
                "Please add this vessel to the live map.",
            ]]},
            {"cells": [{"value": value} for value in [
                "", "9876543", "Cargo vessel", "Spain", "—",
            ]]},
        ],
    })
    return {name: models[name] for name in ("reviews", "survey_marine", "conversion")}


def write_mobile_previews(output_directory):
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    for digest, model in mobile_fixture_models().items():
        _, html = render_fixture(digest, model)
        name = "survey" if digest == "survey_marine" else digest
        (output_directory / f"b-{name}.html").write_text(html, encoding="utf-8")
    print("Rendered 3 synthetic mobile fixture previews")


def write_previews(output_directory):
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    for digest, model in fixture_models().items():
        _, html = render_fixture(digest, model)
        (output_directory / f"{digest}.html").write_text(html, encoding="utf-8")
    print("Rendered 5 synthetic fixture previews")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--mobile":
        write_mobile_previews(sys.argv[2])
    elif len(sys.argv) == 2:
        write_previews(sys.argv[1])
    else:
        raise SystemExit("Usage: python3 tests/render_fixtures.py [--mobile] <output-directory>")
