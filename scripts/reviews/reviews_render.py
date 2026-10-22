#!/usr/bin/env python3
"""Pure app review renderer built on the shared email shell."""
from scripts.common import email_shell as shell


def _rating_color(rating):
    if rating >= 4:
        return shell.GREEN
    if rating >= 3:
        return shell.AMBER
    return shell.RED if rating > 0 else shell.MUTED


def _review_card(review):
    """Compose a review card using the shell's text and dark-mode hooks."""
    rating = max(0, min(5, int(review.get("rating", 0))))
    stars = (
        f'<p style="margin:0; font-family:{shell.FONT_HEADING}; font-size:16px; '
        f'font-weight:600; color:{_rating_color(rating)};">'
        f'{"★" * rating}<span style="color:{shell.RULE};">{"☆" * (5 - rating)}</span>'
        f'<span style="font-size:12px;" class="text-muted"> {rating}/5</span></p>'
    )
    parts = [stars]
    if review.get("title"):
        parts.append(shell.h3(review["title"]))
    parts.append(shell.p(review.get("body", "")))
    if review.get("store") == "appstore":
        store_meta = [review.get("country", "")]
    else:
        store_meta = [review.get("device", ""), review.get("os_version", "")]
    meta = store_meta + [review.get("author", ""), review.get("version", "")]
    parts.append(shell.small(" · ".join(str(value) for value in meta if value)))
    if review.get("is_non_english"):
        parts.append(shell.badge("Non-English", "muted"))
    contents = ''.join(
        '<tr><td style="padding:8px 0 0 0;">' + part + '</td></tr>'
        for part in parts
    )
    return shell.cell(
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">'
        f'<tr><td bgcolor="{shell.CARD}" style="background-color:{shell.CARD}; '
        'padding:8px 20px 16px 20px;" class="stat-card-dm">'
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">'
        + contents + '</table></td></tr></table>',
        "12px 40px 0 40px",
    )


def render(model):
    """Return the metric tail and HTML body; the caller composes the subject."""
    m = model
    count = m["grand_total"]
    tail = f"{count} review{'s' if count != 1 else ''} with 3★ or under"
    preheader = f"{tail} from {m.get('total_fetched', count)} total across {len(m['apps'])} apps"
    body = shell.masthead(
        "Daily review digest", "App reviews", lead=m["date_str"],
        caption=f"{preheader} · Since {m['since_str']}",
    )
    body += shell.section_open()
    body += shell.cell(" &nbsp; ".join(shell.badge(name) for name in m["app_names"]))
    body += shell.cell(shell.stat_grid([
        (f"{app['avg_rating']:.1f} ★" if app["count"] else "—",
         f"{app['name']} · {app['count']} review{'s' if app['count'] != 1 else ''}",
         _rating_color(app["avg_rating"]))
        for app in m["apps"]
    ]), "24px 40px 0 40px")
    for app in m["apps"]:
        body += shell.cell(shell.divider(), "32px 40px 0 40px")
        body += shell.cell(shell.h2(app["name"]))
        if not app["count"]:
            body += shell.cell(shell.small("No new reviews"))
            continue
        body += shell.cell(shell.small(
            f"{app['count']} review{'s' if app['count'] != 1 else ''} with 3★ or under"
        ), "8px 40px 0 40px")
        for label, key in (("App Store", "appstore_reviews"), ("Play Store", "playstore_reviews")):
            reviews = app[key]
            if reviews:
                body += shell.cell(shell.h3(f"{label} · {len(reviews)}"), "20px 40px 0 40px")
                body += ''.join(_review_card(review) for review in reviews)
    body += shell.section_close() + shell.spacer()
    return tail, shell.document(
        "App reviews", preheader, body,
        shell.footer("App reviews digest", ["Sent automatically by Lascade"], [
            ("App Store Connect", "https://appstoreconnect.apple.com"),
            ("Play Console", "https://play.google.com/console"),
        ]),
    )
