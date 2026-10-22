#!/usr/bin/env python3
"""Pure install-to-paid renderer with the shared shell and cohort charts."""
import json
import math
from html import escape
from urllib.parse import quote

from scripts.common import email_shell as shell
from scripts.conversion.conversion_model import format_pct, format_num, format_cohort_date

ADAPTY_DASHBOARD = "https://app.adapty.io"
CHART_FONT = "Inter, 'Segoe UI', sans-serif"


def _rate_color(rate):
    if rate >= 5:
        return shell.GREEN
    if rate >= 2:
        return shell.AMBER
    return shell.RED


def _axis_ticks(rates):
    """Keep adjacent ticks at least one displayed decimal unit apart."""
    low, high = min(rates), max(rates)
    precision = 2 if high - low < 1 else 1
    scale = 10 ** precision
    step_units = max(1, math.ceil((high - low) * scale / 4))
    # Integer decimal units avoid rounding a minimum upward or maximum down.
    low_units = math.floor(round(low * scale, 8) / step_units) * step_units
    high_units = math.ceil(round(high * scale, 8) / step_units) * step_units
    if low_units == high_units:
        high_units += step_units
    return {
        "min": low_units / scale, "max": high_units / scale,
        "stepSize": step_units / scale, "precision": precision,
        "callback": "__TICK_CB__", "fontColor": shell.STAT_LABEL,
        "fontSize": 11, "fontFamily": CHART_FONT,
    }


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
    last_color = shell.RED
    ticks = _axis_ticks(rates)

    pt_bg = [shell.INK] * (n - 1) + [last_color]
    pt_r = [2] * (n - 1) + [6]
    pt_bc = [shell.INK] * (n - 1) + ["#ffffff"]
    pt_bw = [0] * (n - 1) + [2]
    dl_display = [False] * (n - 1) + [True]

    config = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [{
                "data": rates,
                "borderColor": shell.INK,
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
                    "ticks": ticks,
                    "gridLines": {"color": shell.RULE, "zeroLineColor": shell.RULE},
                }],
                "xAxes": [{
                    "ticks": {"maxTicksLimit": 5, "fontColor": shell.STAT_LABEL,
                              "fontSize": 11, "fontFamily": CHART_FONT},
                    "gridLines": {"display": False, "color": shell.RULE, "zeroLineColor": shell.RULE},
                }],
            },
            "plugins": {
                "datalabels": {
                    "display": dl_display,
                    "align": "top",
                    "color": last_color,
                    "font": {"family": CHART_FONT, "weight": "bold", "size": 12},
                    "formatter": "__FMT_CB__",
                },
            },
        },
    }

    cfg = json.dumps(config, separators=(",", ":"))
    formatter = "function(v){return v.toFixed(" + str(ticks["precision"]) + ")+'%'}"
    cfg = cfg.replace('"__TICK_CB__"', formatter)
    cfg = cfg.replace('"__FMT_CB__"', formatter)

    url = ("https://quickchart.io/chart?c=" + quote(cfg)
           + "&amp;w=520&amp;h=150&amp;bkg=%23ffffff")

    alt = f"{app['name']} conversion: {format_pct(pts[-1]['rate'])}%"
    # The reference's Images & Figures component uses a presentation table,
    # a fluid image, and a centered 13px caption in the next row.
    return (
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">'
        '<tr><td style="padding:0;">'
        f'<img src="{url}" alt="{escape(alt)}" width="520" height="150" '
        'style="display:block; width:100%; max-width:520px; height:auto; border-radius:4px;" class="fluid" />'
        '</td></tr><tr>'
        f'<td style="padding:8px 0 0 0; font-family:{shell.FONT_BODY}; '
        'font-size:13px; line-height:1.4; color:#666666; text-align:center;" class="text-muted">'
        f'Daily install→paid rate, last {n} cohorts'
        '</td></tr></table>'
    )


def _stats(app):
    """Compose the template's four-column stat row without an extra wrapper."""
    intro = (
        '<p style="margin:0; Margin:0 0 20px 0; '
        f'font-family:{shell.FONT_BODY}; font-size:16px; line-height:1.6; '
        'letter-spacing:0.01em; color:#222222; text-align:left;" class="text-main">'
        f"{format_num(app['total_paid'])} paid · {format_num(app['total_installs'])} installs"
        '</p>'
    )
    grid = shell.stat_grid([
        (f"{format_pct(app['overall_rate'])}%", "Install → Paid", _rate_color(app["overall_rate"])),
        (format_num(app["total_installs"]), "Installs", shell.INK),
        (format_num(app["total_paid"]), "Paid", shell.GREEN),
        (len(app["cohorts"]), "Cohort days", shell.BLUE),
    ])
    grid = grid.removeprefix('<div style="font-size:0; text-align:center;">\n').removesuffix('</div>\n')
    grid = grid.replace('\n<![endif]-->\n<!--[if mso]>\n', '\n')
    return shell.cell(intro + grid, "16px 40px 0 40px; font-size:0; text-align:center")


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
    )
    body += shell.section_open()
    for app in m["apps"]:
        body += shell.cell(shell.h2(app["name"]), "32px 40px 0 40px")
        if not app["has_data"]:
            body += shell.cell(shell.callout("info", "No conversion data",
                "No conversion data available for this reporting period."))
            continue
        body += _stats(app)
        chart = _line_chart(app)
        if chart:
            body += shell.cell(chart)
        else:
            body += shell.cell(shell.callout("info", "Not enough cohorts",
                "At least two install-date cohorts are needed to show a trend."))
    body += shell.cell(shell.h2("Conversion dashboard"), "32px 40px 0 40px")
    body += shell.cell(shell.button("View in Adapty", ADAPTY_DASHBOARD))
    body += shell.section_close() + shell.spacer()
    return tail, shell.document(
        "Install → Paid", preheader, body,
        shell.footer("Install → Paid digest", [
            "Conversion by install-date cohort; rates grow as users start a subscription.",
            "Sent automatically by Lascade",
        ], [("Adapty dashboard", ADAPTY_DASHBOARD)]),
    )
