#!/usr/bin/env python3
"""Pure HTML renderer for the Install-to-Paid Conversion Digest email.

Same design system as the other digests: Inter font, #f5f3f1 background,
600px container, table-based layout for email client compatibility.

Conversion data is cohort-based: each install-date cohort has a conversion
rate that grows over time as more users from that date convert to their
first subscription.
"""
from html import escape
from conversion_model import format_pct, format_num, format_cohort_date

F = "'Inter',system-ui,-apple-system,'Segoe UI',Roboto,'Helvetica Neue',sans-serif"
FH = "'Inter',system-ui,-apple-system,'Segoe UI',sans-serif"
ADAPTY_DASHBOARD = "https://app.adapty.io"


def _rate_color(rate):
    if rate >= 5:
        return "#2a8c4a"
    if rate >= 2:
        return "#c9922a"
    return "#c0392b"


def _line_chart(app):
    """Inline SVG sparkline of cohort conversion rates over the lookback window.

    Renders chronologically (oldest left, newest right) with the most recent
    data point highlighted. Progressive enhancement — clients that strip SVG
    (Gmail, Outlook) still see the data table below.
    """
    cohorts = app["cohorts"]
    if len(cohorts) < 2:
        return ""

    pts = list(reversed(cohorts))
    n = len(pts)
    rates = [p["rate"] for p in pts]

    W, H = 520, 130
    PL, PR, PT, PB = 40, 20, 22, 24

    r_min, r_max = min(rates), max(rates)
    r_span = r_max - r_min
    if r_span < 0.3:
        r_mid = (r_max + r_min) / 2
        r_min, r_max = r_mid - 0.2, r_mid + 0.2
    else:
        r_min = max(0, r_min - r_span * 0.15)
        r_max += r_span * 0.2
    r_span = r_max - r_min

    pw, ph = W - PL - PR, H - PT - PB

    def sx(i):
        return PL + (i / (n - 1)) * pw

    def sy(r):
        return PT + (1 - (r - r_min) / r_span) * ph

    coords = [(sx(i), sy(r)) for i, r in enumerate(rates)]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)

    lx, ly = coords[-1]
    lr = pts[-1]["rate"]
    lc = _rate_color(lr)

    s = []
    a = s.append

    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
      f'viewBox="0 0 {W} {H}" style="display:block;width:100%;height:auto;">')

    for frac in [0, 0.5, 1.0]:
        val = r_min + frac * r_span
        y = sy(val)
        a(f'<line x1="{PL}" y1="{y:.1f}" x2="{W - PR}" y2="{y:.1f}" '
          f'stroke="#e8e6e3" stroke-width="1"/>')
        a(f'<text x="{PL - 6}" y="{y:.1f}" text-anchor="end" '
          f'dominant-baseline="middle" fill="#aaa" '
          f'font-family="Inter,system-ui,sans-serif" font-size="9">'
          f'{val:.1f}%</text>')

    base_y = PT + ph
    area = (f"{coords[0][0]:.1f},{base_y:.1f} {poly} "
            f"{coords[-1][0]:.1f},{base_y:.1f}")
    a(f'<polygon points="{area}" fill="#222" fill-opacity="0.04"/>')

    a(f'<polyline points="{poly}" fill="none" stroke="#555" '
      f'stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>')

    for x, y in coords[:-1]:
        a(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="#555"/>')

    a(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="5" fill="{lc}" '
      f'stroke="#fff" stroke-width="2"/>')
    label_y = ly - 12 if ly - 12 > 8 else ly + 16
    a(f'<text x="{lx:.1f}" y="{label_y:.1f}" text-anchor="end" fill="{lc}" '
      f'font-family="Inter,system-ui,sans-serif" font-size="11" '
      f'font-weight="700">{format_pct(lr)}%</text>')

    for idx, anchor in [(0, "start"), (n - 1, "end")]:
        a(f'<text x="{sx(idx):.1f}" y="{H - 4}" text-anchor="{anchor}" '
          f'fill="#aaa" font-family="Inter,system-ui,sans-serif" font-size="9">'
          f'{escape(format_cohort_date(pts[idx]["date"]))}</text>')
    if n > 4:
        mid = n // 2
        a(f'<text x="{sx(mid):.1f}" y="{H - 4}" text-anchor="middle" '
          f'fill="#aaa" font-family="Inter,system-ui,sans-serif" font-size="9">'
          f'{escape(format_cohort_date(pts[mid]["date"]))}</text>')

    a('</svg>')
    return "".join(s)


def render(model):
    """Return (subject_line, html_body) from a model dict."""
    m = model

    rate_parts = [f"{a['name']} {format_pct(a['overall_rate'])}%"
                  for a in m["apps"] if a["has_data"]]
    subject = (f"Install → Paid — {', '.join(rate_parts)}"
               if rate_parts else "Install → Paid Conversion Report")

    preheader_parts = []
    for a in m["apps"]:
        if a["has_data"]:
            preheader_parts.append(
                f"{a['name']} {format_pct(a['overall_rate'])}% "
                f"({format_num(a['total_paid'])} paid / {format_num(a['total_installs'])} installs)")
    preheader = " · ".join(preheader_parts) if preheader_parts else "Conversion Report"

    h = []
    _a = h.append

    # Head
    _a('<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" '
       '"http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">')
    _a('<html xmlns="http://www.w3.org/1999/xhtml" lang="en" dir="ltr"><head>')
    _a('<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>')
    _a('<meta http-equiv="X-UA-Compatible" content="IE=edge"/>')
    _a('<meta name="color-scheme" content="light"/><meta name="supported-color-schemes" content="light"/>')
    _a('<meta name="format-detection" content="telephone=no,date=no,address=no,email=no"/>')
    _a('<title>Install to Paid Conversion</title>')
    _a('<!--[if mso]><noscript><xml><o:OfficeDocumentSettings><o:AllowPNG/>'
       '<o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml>'
       '</noscript><![endif]-->')
    _a('<!--[if !mso]><!--><style>@import url("https://fonts.googleapis.com/'
       'css2?family=Inter:wght@400;500;600;700&display=swap");</style><!--<![endif]-->')
    _a('<!--[if mso]><style>body,table,td,th,p,li,a,span{font-family:"Segoe UI",'
       'Arial,sans-serif!important;}h1,h2,h3{font-family:"Segoe UI",Arial,'
       'sans-serif!important;}</style><![endif]-->')
    _a('<style>')
    _a('#outlook a{padding:0}'
       'body{margin:0!important;padding:0!important;width:100%!important;'
       '-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%}'
       'table{border-collapse:collapse;mso-table-lspace:0pt;mso-table-rspace:0pt}'
       'td{border-collapse:collapse}p{margin:0;Margin:0}a{color:#222}'
       '.ExternalClass{width:100%}'
       '.ExternalClass,.ExternalClass p,.ExternalClass span,.ExternalClass font,'
       '.ExternalClass td,.ExternalClass div{line-height:100%}'
       'a[x-apple-data-detectors]{color:inherit!important;text-decoration:none!important}')
    _a('@media only screen and (max-width:480px){'
       '.email-container{width:100%!important;max-width:100%!important}'
       '.body-cell{padding-left:16px!important;padding-right:16px!important}'
       'h1.email-h1{font-size:24px!important}'
       'h2.email-h2{font-size:17px!important}'
       '.stat-col{display:block!important;width:100%!important;max-width:100%!important;'
       'padding:0 0 8px 0!important}'
       '.data-table td,.data-table th{font-size:12px!important;padding:6px 8px!important}}')
    _a('</style></head>')

    # Body open
    _a('<body style="margin:0;padding:0;background-color:#f5f3f1;width:100%;">')
    _a(f'<div style="display:none;font-size:1px;color:#f5f3f1;line-height:1px;'
       f'max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all;">'
       f'{escape(preheader)}&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;</div>')
    _a('<table role="presentation" cellspacing="0" cellpadding="0" border="0" '
       'width="100%" style="background-color:#f5f3f1;"><tr><td align="center" '
       'valign="top" style="padding:20px 10px;">')
    _a('<!--[if mso]><table role="presentation" cellspacing="0" cellpadding="0" '
       'border="0" width="600" align="center"><tr><td><![endif]-->')
    _a('<div style="max-width:600px;width:100%;margin:0 auto;" class="email-container">')

    # --- Header ---
    chips = ""
    for name in m["app_names"]:
        chips += (f'<span style="display:inline-block;font-family:{F};font-size:12px;'
                  f'font-weight:600;color:#555;background:#e8e6e3;padding:3px 10px;'
                  f'border-radius:12px;margin-right:4px;">{escape(name)}</span>')

    _a('<table role="presentation" cellspacing="0" cellpadding="0" border="0" '
       'width="100%" style="background-color:#f5f3f1;">')
    _a(f'<tr><td style="padding:40px 40px 10px 40px;text-align:left;" class="body-cell">'
       f'<p style="margin:0;font-family:{FH};font-size:12px;font-weight:600;'
       f'letter-spacing:0.08em;text-transform:uppercase;color:#888;">'
       f'Daily Conversion Report</p></td></tr>')
    _a(f'<tr><td style="padding:10px 40px 0 40px;" class="body-cell">'
       f'<h1 class="email-h1" style="margin:0;font-family:{FH};font-size:28px;'
       f'font-weight:700;line-height:1.15;letter-spacing:-0.02em;color:#222;">'
       f'Install &rarr; Paid Conversion</h1></td></tr>')
    _a(f'<tr><td style="padding:10px 40px 0 40px;" class="body-cell">'
       f'<p style="margin:0;">{chips}</p></td></tr>')
    _a(f'<tr><td style="padding:8px 40px 0 40px;" class="body-cell">'
       f'<p style="margin:0;font-family:{F};font-size:14px;line-height:1.5;color:#888;">'
       f'{escape(m["date_str"])}</p></td></tr>')
    _a(f'<tr><td style="padding:4px 40px 0 40px;" class="body-cell">'
       f'<p style="margin:0;font-family:{F};font-size:12px;line-height:1.5;color:#aaa;">'
       f'Cohort conversion rates as of today</p></td></tr>')
    _a('<tr><td style="padding:20px 40px 0 40px;" class="body-cell">'
       '<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">'
       '<tr><td style="border-top:2px solid #222;font-size:1px;line-height:1px;">'
       '&nbsp;</td></tr></table></td></tr>')
    _a('</table>')

    # --- Summary cards (one per app) ---
    _a('<table role="presentation" cellspacing="0" cellpadding="0" border="0" '
       'width="100%" style="background-color:#f5f3f1;">')
    _a('<tr><td style="padding:24px 40px 0 40px;" class="body-cell">')
    _a('<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%"><tr>')

    for i, app in enumerate(m["apps"]):
        if i > 0:
            _a('<td style="width:8px;">&nbsp;</td>')
        if app["has_data"]:
            color = _rate_color(app["overall_rate"])
            rate_str = f'{format_pct(app["overall_rate"])}%'
            sub_text = (f'{format_num(app["total_paid"])} paid &middot; '
                        f'{format_num(app["total_installs"])} installs')
        else:
            color = "#aaa"
            rate_str = "&mdash;"
            sub_text = "No API key"
        _a(f'<td style="vertical-align:top;text-align:center;" class="stat-col">'
           f'<table role="presentation" cellspacing="0" cellpadding="0" border="0" '
           f'width="100%" style="background-color:#fff;border-radius:6px;">'
           f'<tr><td style="padding:18px 12px;text-align:center;">'
           f'<p style="margin:0;font-family:{FH};font-size:11px;font-weight:600;'
           f'letter-spacing:0.08em;text-transform:uppercase;color:#888;">{escape(app["name"])}</p>'
           f'<p style="margin:6px 0 0 0;font-family:{FH};font-size:28px;font-weight:700;'
           f'line-height:1.1;letter-spacing:-0.02em;color:{color};">'
           f'{rate_str}</p>'
           f'<p style="margin:4px 0 0 0;font-family:{FH};font-size:11px;color:#888;">'
           f'{sub_text}</p>'
           f'</td></tr></table></td>')

    _a('</tr></table></td></tr></table>')

    # --- Per-app chart sections ---
    for app in m["apps"]:
        if not app["has_data"]:
            _a(_app_no_data(app["name"]))
            continue
        _a(_cohort_section(app))

    # --- Footer ---
    _a('<table role="presentation" cellspacing="0" cellpadding="0" border="0" '
       'width="100%" style="background-color:#f5f3f1;">')
    _a('<tr><td style="padding:28px 40px 0 40px;" class="body-cell">'
       '<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">'
       '<tr><td style="border-top:2px solid #222;font-size:1px;line-height:1px;">'
       '&nbsp;</td></tr></table></td></tr>')
    _a(f'<tr><td style="padding:18px 40px 8px 40px;text-align:center;" class="body-cell">'
       f'<table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center">'
       f'<tr><td style="border-radius:4px;background-color:#222;">'
       f'<a href="{ADAPTY_DASHBOARD}" target="_blank" style="display:inline-block;'
       f'padding:10px 24px;font-family:{FH};font-size:13px;font-weight:600;color:#fff;'
       f'text-decoration:none;letter-spacing:0.01em;">View in Adapty &#8599;</a>'
       f'</td></tr></table></td></tr>')
    _a(f'<tr><td style="padding:8px 40px 40px 40px;text-align:center;" class="body-cell">'
       f'<p style="margin:0;font-family:{F};font-size:12px;line-height:1.5;color:#aaa;">'
       f'Sent automatically by Lascade &middot; Conversion Report</p></td></tr>')
    _a('</table>')

    # Close
    _a('</div>')
    _a('<!--[if mso]></td></tr></table><![endif]-->')
    _a('</td></tr></table></body></html>')

    return subject, "".join(h)


def _cohort_section(app):
    """Render the app heading + line chart (no data table)."""
    h = []
    _a = h.append

    _a('<table role="presentation" cellspacing="0" cellpadding="0" border="0" '
       'width="100%" style="background-color:#f5f3f1;">')
    _a(f'<tr><td style="padding:28px 40px 0 40px;" class="body-cell">'
       f'<h2 class="email-h2" style="margin:0;font-family:{FH};font-size:18px;'
       f'font-weight:700;line-height:1.3;color:#222;">{escape(app["name"])}</h2>'
       f'</td></tr>')
    chart = _line_chart(app)
    if chart:
        _a(f'<tr><td style="padding:10px 40px 0 40px;" class="body-cell">'
           f'<table role="presentation" cellspacing="0" cellpadding="0" border="0" '
           f'width="100%" style="background-color:#fff;border-radius:6px;">'
           f'<tr><td style="padding:16px 14px 12px 14px;">'
           f'{chart}'
           f'</td></tr></table></td></tr>')
    _a('</table>')
    return "".join(h)


def _app_no_data(name):
    """Render a placeholder card when an app has no API key configured."""
    return (f'<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" '
            f'style="background-color:#f5f3f1;">'
            f'<tr><td style="padding:28px 40px 0 40px;" class="body-cell">'
            f'<h2 class="email-h2" style="margin:0;font-family:{FH};font-size:18px;'
            f'font-weight:700;line-height:1.3;color:#222;">{escape(name)}</h2></td></tr>'
            f'<tr><td style="padding:8px 40px 0 40px;" class="body-cell">'
            f'<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" '
            f'style="background-color:#ffffff;border-radius:6px;">'
            f'<tr><td style="padding:18px 24px;text-align:center;">'
            f'<p style="margin:0;font-family:{F};font-size:13px;color:#aaa;">'
            f'No API key configured</p>'
            f'</td></tr></table></td></tr></table>')
