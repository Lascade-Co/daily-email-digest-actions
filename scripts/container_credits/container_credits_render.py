#!/usr/bin/env python3
"""Pure container tracking credit purchase renderer built on the shared email shell."""
from scripts.common import email_shell as shell
from scripts.container_credits.container_credits_model import format_money, format_num

ADAPTY_DASHBOARD = "https://app.adapty.io"


def render(model):
    """Return the metric tail and HTML body; the caller composes the subject."""
    m = model
    tail = (f"${format_money(m['today_revenue'])} "
            f"({m['today_count']} purchase{'s' if m['today_count'] != 1 else ''})")
    preheader = f"{tail} · ${format_money(m['month_revenue'])} month to date"
    body = shell.masthead(
        "Daily credit purchase digest", "Container Tracking Credits",
        lead=f"{m['date_str']} · Since {m['cutoff_str']}",
    )
    body += shell.section_open()
    body += shell.cell(shell.h2("Purchases at a Glance"), "32px 40px 0 40px")
    summary = shell.p(
        f"${format_money(m['today_revenue'])} net revenue · "
        f"{format_num(m['today_count'])} purchases"
    ).replace("Margin:0;", "Margin:0 0 20px 0;", 1).replace(
        "color:#222222;", "color:#222222; text-align:left;", 1
    )
    stats = shell.stat_grid([
        (format_num(m["today_count"]), "Today", shell.GREEN),
        (f"${format_money(m['today_revenue'])}", "Revenue", shell.INK),
        (format_num(m["month_count"]), "MTD sales", shell.BLUE),
        (f"${format_money(m['month_revenue'])}", "MTD revenue", shell.INK),
    ])
    stats = stats.removeprefix('<div style="font-size:0; text-align:center;">\n')
    stats = stats.removesuffix('</div>\n')
    stats = stats.replace('\n<![endif]-->\n<!--[if mso]>\n', '\n')
    body += (
        '<tr><td style="padding:16px 40px 0 40px; font-size:0; text-align:center;" '
        'class="body-cell">' + summary + stats + '</td></tr>\n'
    )
    today_products = [p for p in m["products"] if p["today_count"] > 0]
    if today_products:
        body += shell.cell(shell.h2("Credit Pack Breakdown"), "32px 40px 0 40px")
        body += shell.cell(shell.table(
            ["Pack", "Count", "Revenue"],
            [[p["name"], format_num(p["today_count"]),
              f"${format_money(p['today_revenue'])}"]
             for p in today_products],
            aligns=["left", "right", "right"],
        ))
    body += shell.cell(shell.h2("Month to Date"), "32px 40px 0 40px")
    body += shell.cell(shell.small(m["month_label"]))
    month_products = [p for p in m["products"] if p["month_count"] > 0]
    if month_products:
        body += shell.cell(shell.table(
            ["Pack", "Count", "Revenue"],
            [[p["name"], format_num(p["month_count"]),
              f"${format_money(p['month_revenue'])}"]
             for p in month_products]
            + [["Total", format_num(m["month_count"]),
                f"${format_money(m['month_revenue'])}"]],
            aligns=["left", "right", "right"],
        ))
    else:
        body += shell.cell(shell.callout(
            "info", "No purchases", "No container credit purchases this month yet."))
    body += shell.cell(shell.button("View in Adapty", ADAPTY_DASHBOARD))
    body += shell.section_close() + shell.spacer()
    return tail, shell.document(
        "Container Tracking Credits", preheader, body,
        shell.footer(
            "Container credit purchase digest",
            ["Daily container tracking credit purchases from Adapty (net revenue).",
             "Sent automatically by Lascade"],
            links=[("Adapty dashboard", ADAPTY_DASHBOARD)],
        ),
    )
