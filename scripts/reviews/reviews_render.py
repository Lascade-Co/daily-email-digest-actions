#!/usr/bin/env python3
"""Pure app review renderer built on the shared email shell."""
from html import escape

from scripts.common import email_shell as shell


def _rating_color(rating):
    if rating >= 4:
        return shell.GREEN
    if rating >= 3:
        return shell.AMBER
    return shell.RED if rating > 0 else shell.MUTED


def _review_card(review):
    """Use the style guide's Text Card with its caption and muted badge."""
    rating = max(0, min(5, int(review.get("rating", 0))))
    title = f'{"★" * rating}{"☆" * (5 - rating)} · {rating}/5'
    if review.get("title"):
        title += f" · {review['title']}"
    if review.get("store") == "appstore":
        store_meta = [review.get("country", "")]
    else:
        store_meta = [review.get("device", ""), review.get("os_version", "")]
    meta = store_meta + [review.get("author", ""), review.get("version", "")]
    metadata = shell.small(" · ".join(str(value) for value in meta if value))
    if review.get("is_non_english"):
        metadata = metadata.removesuffix("</p>") + " &nbsp; " + shell.badge("Non-English", "muted") + "</p>"
    return shell.cell(
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" '
        'style="border-radius:6px; box-shadow:0 2px 8px rgba(0,0,0,0.08);">'
        '<tr><td bgcolor="#fefefe" style="background-color:#fefefe; padding:24px; '
        'border-radius:6px;" class="card-bg">'
        '<h4 class="heading-dm" style="margin:0; Margin:0 0 8px 0; '
        f'font-family:{shell.FONT_HEADING}; font-size:16px; font-weight:600; '
        'line-height:1.4; color:#222222;">' + escape(title) + '</h4>'
        '<p style="margin:0; Margin:0 0 12px 0; '
        f'font-family:{shell.FONT_BODY}; font-size:15px; line-height:1.6; '
        'color:#222222;" class="text-main">' + escape(str(review.get("body", ""))) + '</p>'
        + metadata + '</td></tr></table>',
    )


def render(model):
    """Return the metric tail and HTML body; the caller composes the subject."""
    m = model
    count = m["grand_total"]
    tail = f"{count} review{'s' if count != 1 else ''} with 3★ or under"
    preheader = f"{tail} from {m.get('total_fetched', count)} total across {len(m['apps'])} apps"
    body = shell.masthead(
        "Daily review digest", "App reviews", lead=m["date_str"],
    )
    body += shell.section_open()
    body += shell.cell(shell.h2("Review summary"), "32px 40px 0 40px")
    summary = shell.p(f"{preheader} · Since {m['since_str']}").replace(
        "Margin:0;", "Margin:0 0 20px 0;", 1
    ).replace("color:#222222;", "color:#222222; text-align:left;", 1)
    grid = shell.stat_grid([
        (count, "Reviews ≤3★", shell.INK),
        (f"{m['overall_avg']:.1f} ★" if count else "—", "Average rating", _rating_color(m["overall_avg"])),
        (sum(len(app["appstore_reviews"]) for app in m["apps"]), "App Store", shell.INK),
        (sum(len(app["playstore_reviews"]) for app in m["apps"]), "Play Store", shell.INK),
    ])
    # The template places the grid's layout styles on the body cell itself.
    grid = grid.removeprefix('<div style="font-size:0; text-align:center;">\n').removesuffix('</div>\n')
    grid = grid.replace('\n<![endif]-->\n<!--[if mso]>\n', '\n')
    body += ('<tr><td style="padding:16px 40px 0 40px; font-size:0; text-align:center;" '
             'class="body-cell">' + summary + grid + '</td></tr>\n')
    for app in m["apps"]:
        body += shell.cell(shell.h2(app["name"]), "32px 40px 0 40px")
        if not app["count"]:
            body += shell.cell(shell.small("No new reviews"))
            continue
        body += shell.cell(shell.small(
            f"{app['count']} review{'s' if app['count'] != 1 else ''} with 3★ or under"
            f" · Average rating {app['avg_rating']:.1f} ★"
        ))
        for label, key in (("App Store", "appstore_reviews"), ("Play Store", "playstore_reviews")):
            reviews = app[key]
            if reviews:
                body += shell.cell(shell.h3(f"{label} · {len(reviews)}"))
                body += ''.join(_review_card(review) for review in reviews)
    body += shell.section_close() + shell.spacer()
    return tail, shell.document(
        "App reviews", preheader, body,
        shell.footer("App reviews digest", [
            "App Store and Play Store reviews with 3★ or under.",
            "Sent automatically by Lascade",
        ], [
            ("App Store Connect", "https://appstoreconnect.apple.com"),
            ("Play Console", "https://play.google.com/console"),
        ]),
    )
