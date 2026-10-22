#!/usr/bin/env python3
"""Pure install-to-paid renderer with the shared shell and cohort charts."""
import json
from html import escape
from urllib.parse import quote

from scripts.common import email_shell as shell
from scripts.conversion.conversion_model import format_pct, format_num, format_cohort_date

ADAPTY_DASHBOARD = "https://app.adapty.io"


def _rate_color(rate):
    if rate >= 5:
        return shell.GREEN
    if rate >= 2:
        return shell.AMBER
    return shell.RED


def _line_chart(app):
    """Line chart rendered as a PNG image via QuickChart.io.

    QuickChart renders Chart.js configs server-side, returning a PNG that
    works in every email client including Gmail and Outlook.
    """
    cohorts = app["cohorts"]
    if len(cohorts) < 2:
        return ""

    pts = list(reversed(cohorts))
    n = len(pts)
    labels = [format_cohort_date(p["date"]) for p in pts]
    rates = [round(p["rate"], 2) for p in pts]
    last_color = _rate_color(pts[-1]["rate"])

    pt_bg = ["#888"] * (n - 1) + [last_color]
    pt_r = [2] * (n - 1) + [6]
    pt_bc = ["#888"] * (n - 1) + ["#fff"]
    pt_bw = [0] * (n - 1) + [2]
    dl_display = [False] * (n - 1) + [True]

    config = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [{
                "data": rates,
                "borderColor": "#888",
                "borderWidth": 1.5,
                "pointBackgroundColor": pt_bg,
                "pointRadius": pt_r,
                "pointBorderColor": pt_bc,
                "pointBorderWidth": pt_bw,
                "fill": False,
                "lineTension": 0.3,
            }],
        },
        "options": {
            "legend": {"display": False},
            "scales": {
                "yAxes": [{
                    "ticks": {
                        "callback": "__TICK_CB__",
                        "fontColor": "#aaa",
                        "fontSize": 10,
                    },
                    "gridLines": {"color": "#e8e6e3", "zeroLineColor": "#e8e6e3"},
                }],
                "xAxes": [{
                    "ticks": {"maxTicksLimit": 5, "fontColor": "#aaa", "fontSize": 9},
                    "gridLines": {"display": False},
                }],
            },
            "plugins": {
                "datalabels": {
                    "display": dl_display,
                    "align": "top",
                    "color": last_color,
                    "font": {"weight": "bold", "size": 12},
                    "formatter": "__FMT_CB__",
                },
            },
        },
    }

    cfg = json.dumps(config, separators=(",", ":"))
    cfg = cfg.replace('"__TICK_CB__"', "function(v){return v.toFixed(1)+'%'}")
    cfg = cfg.replace('"__FMT_CB__"', "function(v){return v.toFixed(1)+'%'}")

    url = ("https://quickchart.io/chart?c=" + quote(cfg)
           + "&amp;w=520&amp;h=150&amp;bkg=%23ffffff")

    alt = f"{app['name']} conversion: {format_pct(pts[-1]['rate'])}%"
    return (f'<img src="{url}" width="520" '
            f'style="display:block;width:100%;height:auto;" '
            f'alt="{escape(alt)}" />')


def render(model):
    """Return the metric tail and HTML body; the caller composes the subject."""
    m = model
    rate_parts = [f"{app['name']} {format_pct(app['overall_rate'])}%"
                  for app in m["apps"] if app["has_data"]]
    tail = ", ".join(rate_parts) if rate_parts else "No conversion data"
    preheader_parts = [
        f"{app['name']} {format_pct(app['overall_rate'])}% "
        f"({format_num(app['total_paid'])} paid / {format_num(app['total_installs'])} installs)"
        for app in m["apps"] if app["has_data"]
    ]
    preheader = " · ".join(preheader_parts) if preheader_parts else "No conversion data"
    body = shell.masthead(
        "Daily conversion digest", "Install → Paid", lead=m["date_str"],
        caption="Conversion by install-date cohort; rates grow as users start a subscription.",
    )
    body += shell.section_open()
    body += shell.cell(" &nbsp; ".join(shell.badge(name) for name in m["app_names"]))
    body += shell.cell(shell.stat_grid([
        (f"{format_pct(app['overall_rate'])}%" if app["has_data"] else "—",
         app["name"], _rate_color(app["overall_rate"]) if app["has_data"] else shell.MUTED)
        for app in m["apps"]
    ]), "24px 40px 0 40px")
    for app in m["apps"]:
        body += shell.cell(shell.h2(app["name"]), "32px 40px 0 40px")
        if not app["has_data"]:
            body += shell.cell(shell.small("No conversion data available for this reporting period."))
            continue
        body += shell.cell(shell.small(
            f"{format_num(app['total_paid'])} paid · {format_num(app['total_installs'])} installs"
        ), "8px 40px 0 40px")
        chart = _line_chart(app)
        if chart:
            body += shell.cell(chart)
        else:
            body += shell.cell(shell.small("At least two install-date cohorts are needed to show a trend."))
    body += shell.cell(shell.button("View in Adapty", ADAPTY_DASHBOARD), "32px 40px 0 40px")
    body += shell.section_close() + shell.spacer()
    return tail, shell.document(
        "Install → Paid", preheader, body,
        shell.footer("Install → Paid digest", ["Sent automatically by Lascade"]),
    )
