#!/usr/bin/env python3
"""Pure MarineRadar revenue renderer built on the shared email shell."""
from scripts.common import email_shell as shell
from scripts.revenue.revenue_model import format_money

STRIPE_DASHBOARD = "https://dashboard.stripe.com/payments"


def render(model):
    """Return the metric tail and HTML body; the caller composes the subject."""
    m = model
    tail = (f"${format_money(m['today_total'])} "
            f"({m['today_count']} purchase{'s' if m['today_count'] != 1 else ''})")
    preheader = f"{tail} · ${format_money(m['month_total'])} month to date"
    body = shell.masthead(
        "Daily revenue digest", "MarineRadar web revenue",
        lead=f"{m['date_str']} · Since {m['cutoff_str']}",
    )
    body += shell.section_open()
    body += shell.cell(shell.h2("Revenue at a Glance"), "32px 40px 0 40px")
    summary = shell.p(
        f"${format_money(m['today_total'])} revenue · "
        f"${format_money(m['today_refund_total'])} refunded"
    ).replace("Margin:0;", "Margin:0 0 20px 0;", 1).replace(
        "color:#222222;", "color:#222222; text-align:left;", 1
    )
    stats = shell.stat_grid([
        (m["today_count"], "Purchases", shell.GREEN),
        (m["today_refund_count"], "Refunds", shell.RED),
        (m["month_count"], "MTD sales", shell.INK),
        (m["month_refund_count"], "MTD refunds", shell.RED),
    ])
    # The reference places zero font size and centering on the body cell,
    # directly around the four-column MSO ghost table and metric cards.
    stats = stats.removeprefix('<div style="font-size:0; text-align:center;">\n')
    stats = stats.removesuffix('</div>\n')
    stats = stats.replace('\n<![endif]-->\n<!--[if mso]>\n', '\n')
    body += (
        '<tr><td style="padding:16px 40px 0 40px; font-size:0; text-align:center;" '
        'class="body-cell">' + summary + stats + '</td></tr>\n'
    )
    if m["packs"]:
        body += shell.cell(shell.h2("Credit Pack Breakdown"), "32px 40px 0 40px")
        body += shell.cell(shell.table(
            ["Pack", "Count", "Total"],
            [[f"${pack['amount']}", pack["count"], f"${format_money(pack['total'])}"]
             for pack in m["packs"]],
            aligns=["left", "right", "right"],
        ))
    body += shell.cell(shell.h2("Month to Date"), "32px 40px 0 40px")
    body += shell.cell(shell.small(m["month_label"]))
    body += shell.cell(shell.table(
        ["Metric", "Amount"],
        [["Total Revenue", f"${format_money(m['month_total'])}"],
         ["Total Refunded", f"−${format_money(m['month_refund_total'])}"],
         ["Net Revenue", f"${format_money(m['month_net'])}"]],
        aligns=["left", "right"],
    ))
    body += shell.cell(shell.button("View in Stripe", STRIPE_DASHBOARD))
    body += shell.section_close() + shell.spacer()
    return tail, shell.document(
        "MarineRadar web revenue", preheader, body,
        shell.footer(
            "MarineRadar revenue digest",
            ["Daily credit-pack purchases and refunds from Stripe.",
             "Sent automatically by Lascade"],
            links=[("Stripe dashboard", STRIPE_DASHBOARD)],
        ),
    )
