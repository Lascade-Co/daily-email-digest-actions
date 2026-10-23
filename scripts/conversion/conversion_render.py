#!/usr/bin/env python3
"""Pure install-to-paid renderer with the shared shell and cohort charts."""
from html import escape

from scripts.common import email_shell as shell
from scripts.conversion.conversion_model import format_pct, format_num, format_cohort_date

ADAPTY_DASHBOARD = "https://app.adapty.io"


def _rate_color(rate):
    if rate >= 5:
        return shell.GREEN
    if rate >= 2:
        return shell.AMBER
    return shell.RED


def bar_chart(title, rows):
    """Render the template's Bar Chart, highlighting the final cohort in red."""
    rows = list(rows)
    if not rows:
        return ""
    html = (
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" '
        'bgcolor="#fefefe" style="background-color:#fefefe; padding:0;" class="bar-chart-dm">'
        '<tr><td style="padding:20px;">'
        '<p style="margin:0; Margin:0 0 12px 0; '
        f'font-family:{shell.FONT_HEADING}; font-size:11px; font-weight:600; '
        'text-transform:uppercase; letter-spacing:0.06em; color:#999999;" class="bar-title-dm">'
        + escape(str(title)) + '</p>'
    )
    for index, (label, value_text, fraction) in enumerate(rows):
        width = round(max(0.0, min(1.0, fraction)) * 100, 2)
        color = shell.RED if index == len(rows) - 1 else shell.INK
        spacing = ' style="margin-bottom:8px;"' if index < len(rows) - 1 else ''
        html += (
            '<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%"'
            + spacing + '><tr>'
            f'<td width="130" style="font-family:{shell.FONT_HEADING}; font-size:12px; '
            'font-weight:600; color:#444444; text-align:right; padding-right:10px; '
            'vertical-align:middle;" class="bar-label-cell bar-label-dm">'
            + escape(str(label)) + '</td><td style="vertical-align:middle;">'
            '<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" '
            'bgcolor="#f0eeec" style="background-color:#f0eeec;" class="bar-track-dm"><tr>'
            f'<td width="{width:g}%" bgcolor="{color}" style="background-color:{color}; '
            "height:28px; padding-left:8px; font-family:'Inter', system-ui, sans-serif; "
            'font-size:11px; font-weight:700; color:#ffffff;">'
            + escape(str(value_text)) + f'</td><td width="{100 - width:g}%"></td>'
            '</tr></table></td></tr></table>'
        )
    return html + '</td></tr></table>'


def _days(n):
    return f"{n} day{'s' if n != 1 else ''}"


def _stats(app, window_str, window_days):
    """Compose the template's four-column stat row without an extra wrapper."""
    per_day = (f", about {format_num(app['installs_per_day'])} a day" if window_days > 1 else "")
    intro = (
        '<p style="margin:0; Margin:0 0 20px 0; '
        f'font-family:{shell.FONT_BODY}; font-size:16px; line-height:1.6; '
        'letter-spacing:0.01em; color:#222222; text-align:left;" class="text-main">'
        f"Installs {window_str} ({_days(window_days)}): {format_num(app['total_installs'])} installs"
        f"{per_day}. {format_num(app['total_paid'])} paid to date."
        '</p>'
    )
    grid = shell.stat_grid([
        (f"{format_pct(app['overall_rate'])}%", "Rate", _rate_color(app["overall_rate"])),
        (format_num(app["total_installs"]), "Installs", shell.INK),
        (format_num(app["total_paid"]), "Paid to date", shell.GREEN),
        (format_num(app["installs_per_day"]), "Installs/day", shell.BLUE),
    ])
    grid = grid.removeprefix('<div style="font-size:0; text-align:center;">\n').removesuffix('</div>\n')
    grid = grid.replace('\n<![endif]-->\n<!--[if mso]>\n', '\n')
    return shell.cell(intro + grid, "16px 40px 0 40px; font-size:0; text-align:center")


def render(model):
    """Return the metric tail and HTML body; the caller composes the subject."""
    m = model
    window = f"installs {m['window_str']} ({_days(m['window_days'])}), payments to date"
    rate_parts = [f"{app['name']} {format_pct(app['overall_rate'])}%"
                  for app in m["apps"] if app["has_data"]]
    tail = ", ".join(rate_parts) if rate_parts else "No conversion data"
    preheader_parts = [
        f"{app['name']} {format_pct(app['overall_rate'])}% "
        f"({format_num(app['total_paid'])} paid / {format_num(app['total_installs'])} installs, "
        f"{m['window_str']})"
        for app in m["apps"] if app["has_data"]
    ]
    preheader = " · ".join(preheader_parts) if preheader_parts else "No conversion data"
    body = shell.masthead(
        "Daily conversion digest", "Install → Paid", lead=m["date_str"],
    )
    body += shell.section_open()
    summary_labels = {"marineradar": "MARINE", "smartruler": "RULER", "geoanimator": "GEO"}
    summary = shell.stat_grid([
        (f"{format_pct(app['overall_rate'])}%",
         summary_labels.get(app["name"].replace(" ", "").lower(), app["name"][:10]),
         _rate_color(app["overall_rate"]))
        for app in m["apps"]
    ])
    summary = summary.removeprefix('<div style="font-size:0; text-align:center;">\n').removesuffix('</div>\n')
    summary = summary.replace('\n<![endif]-->\n<!--[if mso]>\n', '\n')
    body += shell.cell(summary, "16px 40px 0 40px; font-size:0; text-align:center")
    body += shell.cell(shell.small(f"Install → paid by app · {window}"))
    for app in m["apps"]:
        body += shell.cell(shell.h2(app["name"]), "32px 40px 0 40px")
        if not app["has_data"]:
            body += shell.cell(shell.callout("info", "No conversion data",
                "No conversion data available for this reporting period."))
            continue
        body += _stats(app, m["window_str"], m["window_days"])
        cohorts = sorted(app["cohorts"], key=lambda cohort: cohort["date"])[-7:]
        if cohorts:
            maximum = max(cohort["rate"] for cohort in cohorts)
            body += shell.cell(bar_chart("Install → paid, latest cohorts (up to 7)", [
                (format_cohort_date(cohort["date"]), f"{cohort['rate']:.2f}%",
                 cohort["rate"] / maximum if maximum > 0 else 0)
                for cohort in cohorts
            ]))
        else:
            body += shell.cell(shell.callout("info", "No cohort data",
                "No install-date cohorts are available for this reporting period."))
    body += shell.cell(shell.h2("Conversion dashboard"), "32px 40px 0 40px")
    body += shell.cell(shell.button("View in Adapty", ADAPTY_DASHBOARD))
    body += shell.section_close() + shell.spacer()
    return tail, shell.document(
        "Install → Paid", preheader, body,
        shell.footer("Install → Paid digest", [
            f"Totals cover installs {m['window_str']} and payments made since; "
            "each cohort's rate grows as its users subscribe.",
            "Sent automatically by Lascade",
        ], [("Adapty dashboard", ADAPTY_DASHBOARD)]),
    )
