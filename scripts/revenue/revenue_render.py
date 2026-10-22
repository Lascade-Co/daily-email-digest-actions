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
        lead=m["date_str"], caption=f"Since {m['cutoff_str']}",
    )
    body += shell.section_open()
    body += shell.cell(shell.lead(
        f"${format_money(m['today_total'])} revenue · "
        f"${format_money(m['today_refund_total'])} refunded"
    ), "24px 40px 0 40px")
    body += shell.cell(shell.stat_grid([
        (m["today_count"], "Purchases", shell.GREEN),
        (m["today_refund_count"], "Refunds", shell.RED),
    ]))
    if m["packs"]:
        body += shell.cell(shell.h2("Credit Pack Breakdown"), "32px 40px 0 40px")
        body += shell.cell(shell.table(
            ["Pack", "Count", "Total"],
            [[f"${pack['amount']}", pack["count"], f"${format_money(pack['total'])}"]
             for pack in m["packs"]],
            aligns=["left", "right", "right"],
        ))
    body += shell.cell(shell.h2("Month to Date"), "32px 40px 0 40px")
    body += shell.cell(shell.small(m["month_label"]), "8px 40px 0 40px")
    body += shell.cell(shell.table(
        ["Metric", "Amount"],
        [["Total Revenue", f"${format_money(m['month_total'])}"],
         ["Total Refunded", f"−${format_money(m['month_refund_total'])}"],
         ["Net Revenue", f"${format_money(m['month_net'])}"]],
        aligns=["left", "right"],
    ))
    body += shell.cell(shell.small(
        f"{m['month_count']} purchases · {m['month_refund_count']} refunds"
    ))
    body += shell.cell(shell.button("View in Stripe", STRIPE_DASHBOARD), "24px 40px 0 40px")
    body += shell.section_close() + shell.spacer()
    return tail, shell.document(
        "MarineRadar web revenue", preheader, body,
        shell.footer("MarineRadar revenue digest", ["Sent automatically by Lascade"]),
    )
