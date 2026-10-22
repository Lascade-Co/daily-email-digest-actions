# COPY of product-intelligence/Style Template/email_shell.py — edit the canonical file, then re-copy.
# sha256(canonical) = c1f320d76cf5
"""Canonical, dependency-free digest email shell (Python 3.9+).

Source: ``Style Template/styleguide-email.html``. The complete head and client
resets are copied verbatim, with only the title placeholder and the donor's
``.tfix`` rule added. Components retain the template's inline styles and hooks.

API and composition:
* FONT_HEADING/FONT_BODY and the named palette constants expose template tokens.
* head(title), open_body(preheader), close_body() build the document envelope.
* section_open()/section_close() enclose rows produced by cell(inner, pad).
* masthead(eyebrow, title, lead=None, caption=None), spacer(), and
  footer(title, lines, links=()) produce complete sections.
* h2(text), h3(text), p(text), lead(text), small(text), table(headers, rows,
  aligns=None, striped=True, widths=None), stat_grid([(value, label, color)]),
  badge(text, variant="default"), callout(kind, title, body),
  button(label, href, secondary=False), and divider() produce inner markup
  for cell(). Stat grids wrap after four fixed 130px columns.
* document(title, preheader, body_html, footer_html) joins the envelope and
  complete sections. It does not insert a masthead, spacer, or footer itself.

All text and attribute arguments are escaped with html.escape. Table headers
and cells are plain text. Only cell's inner and document's body_html/footer_html
are trusted, already-rendered HTML; never put unescaped external data there.
Padding, widths, and stat colors are caller-supplied presentation values.
Footer lines before the final line use the 12px description style; the final
line uses the 11px metadata style. Links are (label, href) pairs at 12px.
Badges: default/outline/muted. Callouts: note/warning/critical/positive/info.
Unknown variants, invalid alignments, and inconsistent table sizes raise
ValueError. All rendering functions are pure and perform no I/O.

Copy rule: edit this canonical file, then copy its complete contents to
``daily-email-digest-actions/scripts/common/email_shell.py`` and
``ta/daily-issues-digest/email_shell.py``, prepending exactly these two lines:
    # COPY of product-intelligence/Style Template/email_shell.py — edit the canonical file, then re-copy.
    # sha256(canonical) = <first 12 hex of the canonical SHA-256>
Run ``bash scripts/check_shell_sync.sh`` before each submodule pointer bump.
Run ``python3 "Style Template/email_shell.py" /tmp/shell-demo.html`` for a demo
of every component; only the command-line entry point writes a file.
"""

from html import escape
from typing import Iterable, List, Optional, Sequence, Tuple, Union

FONT_HEADING = "'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif"
FONT_BODY = "'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif"
BG = "#f5f3f1"
INK = "#222222"
MUTED = "#555555"
CAPTION = "#666666"
RULE = "#dddddd"
STRIPE = "#ece9e6"
CARD = "#fefefe"
STAT_LABEL = "#777777"
GREEN = "#2a8c4a"
RED = "#c0392b"
AMBER = "#c9922a"
BLUE = "#2980b9"

_HEAD = """<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office" lang="en" dir="ltr">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta http-equiv="X-UA-Compatible" content="IE=edge" />
    <meta name="color-scheme" content="light dark" />
    <meta name="supported-color-schemes" content="light dark" />
    <meta name="format-detection" content="telephone=no, date=no, address=no, email=no" />
    <title>__TITLE__</title>

    <!--[if mso]>
    <noscript>
        <xml>
            <o:OfficeDocumentSettings>
                <o:AllowPNG/>
                <o:PixelsPerInch>96</o:PixelsPerInch>
            </o:OfficeDocumentSettings>
        </xml>
    </noscript>
    <![endif]-->

    <!-- Web fonts: hidden from Outlook to prevent Times New Roman fallback -->
    <!--[if !mso]><!-->
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    </style>
    <!--<![endif]-->

    <!-- Outlook-only font fallback -->
    <!--[if mso]>
    <style type="text/css">
        body, table, td, th, p, li, a, span {
            font-family: 'Segoe UI', Arial, sans-serif !important;
        }
        h1, h2, h3, h4, h5, h6 {
            font-family: 'Segoe UI', Arial, sans-serif !important;
        }
    </style>
    <![endif]-->

    <style type="text/css">
        /* ============================================
           EMAIL CLIENT RESETS
           ============================================ */
        #outlook a { padding: 0; }
        body { margin: 0 !important; padding: 0 !important; width: 100% !important; -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }
        table { border-collapse: collapse; mso-table-lspace: 0pt; mso-table-rspace: 0pt; }
        td { border-collapse: collapse; }
        img { border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; display: block; -ms-interpolation-mode: bicubic; }
        p { margin: 0; Margin: 0; }
        a { color: #222222; }
        .ExternalClass { width: 100%; }
        .ExternalClass, .ExternalClass p, .ExternalClass span, .ExternalClass font, .ExternalClass td, .ExternalClass div { line-height: 100%; }

        /* iOS auto-link overrides */
        a[x-apple-data-detectors] {
            color: inherit !important;
            text-decoration: none !important;
            font-size: inherit !important;
            font-family: inherit !important;
            font-weight: inherit !important;
            line-height: inherit !important;
        }

        /* ============================================
           RESPONSIVE
           ============================================ */
        @media only screen and (max-width: 480px) {
            .email-container { width: 100% !important; max-width: 100% !important; }
            .fluid { width: 100% !important; max-width: 100% !important; height: auto !important; }
            .stack-column { display: block !important; width: 100% !important; max-width: 100% !important; direction: ltr !important; }
            .stack-column-center { text-align: center !important; }
            .center-on-narrow { text-align: center !important; display: block !important; margin-left: auto !important; margin-right: auto !important; float: none !important; }
            table.center-on-narrow { display: inline-block !important; }
            .email-container td.body-cell { padding-left: 20px !important; padding-right: 20px !important; }
            .mobile-pad { padding-left: 20px !important; padding-right: 20px !important; }
            h1.email-h1 { font-size: 26px !important; }
            h2.email-h2 { font-size: 20px !important; }
            .mobile-full { width: 100% !important; }
            .mobile-hide { display: none !important; }
            .mobile-show { display: block !important; max-height: none !important; overflow: visible !important; }
            .avatar-col { max-width: 50% !important; width: 50% !important; }
            .avatar-circle { width: 48px !important; height: 48px !important; font-size: 18px !important; line-height: 48px !important; }
            .avatar-name { font-size: 12px !important; }
            .avatar-subtitle { font-size: 11px !important; }
            .stat-col { max-width: 50% !important; width: 50% !important; }
            .stat-value { font-size: 28px !important; }
            .bar-label-cell { width: 100px !important; font-size: 11px !important; }
            .contributor-col { display: block !important; width: 100% !important; max-width: 100% !important; }
        }

        /* ============================================
           DARK MODE — Apple Mail, iOS, macOS Mail
           ============================================ */
        @media (prefers-color-scheme: dark) {
            .body-bg { background-color: #1a1a18 !important; }
            .email-body-bg { background-color: #222220 !important; }
            .card-bg { background-color: #2a2927 !important; }
            .text-main { color: #e0ddd8 !important; }
            .heading-dm { color: #ece9e4 !important; }
            .text-muted { color: #a8a49e !important; }
            .email-link { color: #c8c4be !important; }
            .divider-line { border-color: #3a3835 !important; }
            .code-inline { background-color: #2a2927 !important; color: #e0ddd8 !important; border-color: #3a3835 !important; }
            .footer-bg { background-color: #1a1a18 !important; }
            .callout-info-bg { background-color: #2a2927 !important; border-color: #5a6a9a !important; }
            .callout-warning-bg { background-color: #2a2927 !important; }
            .callout-info-border { background-color: #5a6a9a !important; }
            .badge-bg { background-color: #3a3835 !important; color: #e0ddd8 !important; }
            .badge-outline { border-color: #5a5855 !important; color: #e0ddd8 !important; }
            .mark-bg { background-color: #4a4530 !important; color: #e0ddd8 !important; }
            .kbd-bg { background-color: #3a3835 !important; border-color: #5a5855 !important; color: #e0ddd8 !important; }
            .aside-bg { background-color: #2a2927 !important; }
            .table-stripe { background-color: #2a2927 !important; }
            .table-border { border-color: #3a3835 !important; }
            .btn-primary { background-color: #e0ddd8 !important; color: #1a1a18 !important; border-color: #e0ddd8 !important; }
            .btn-secondary { background-color: transparent !important; color: #e0ddd8 !important; border-color: #e0ddd8 !important; }
            .preheader-bg { background-color: #1a1a18 !important; }
            .header-border { border-color: #3a3835 !important; }
            .blockquote-border { background-color: #5a5855 !important; }
            .pullquote-border { border-color: #5a5855 !important; }
            .img-border { border-color: #3a3835 !important; }
            .avatar-name-dm { color: #ece9e4 !important; }
            .avatar-subtitle-dm { color: #a8a49e !important; }
            .stat-card-dm { background-color: #2a2927 !important; }
            .stat-label-dm { color: #a8a49e !important; }
            .timeline-border-dm { border-color: #3a3835 !important; }
            .timeline-text-dm { color: #e0ddd8 !important; }
            .timeline-time-dm { color: #a8a49e !important; }
            .bar-chart-dm { background-color: #2a2927 !important; }
            .bar-track-dm { background-color: #1a1a18 !important; }
            .bar-label-dm { color: #a8a49e !important; }
            .bar-title-dm { color: #a8a49e !important; }
            .contributor-card-dm { background-color: #2a2927 !important; }
            .contributor-meta-dm { color: #a8a49e !important; }
            .callout-critical-dm { background-color: #2a2220 !important; }
            .callout-positive-dm { background-color: #202a22 !important; }
            .callout-info-dm { background-color: #20242a !important; }
        }

        /* Outlook mobile dark mode */
        [data-ogsc] .body-bg { background-color: #1a1a18 !important; }
        [data-ogsc] .email-body-bg { background-color: #222220 !important; }
        [data-ogsc] .card-bg { background-color: #2a2927 !important; }
        [data-ogsc] .text-main { color: #e0ddd8 !important; }
        [data-ogsc] .heading-dm { color: #ece9e4 !important; }
        [data-ogsc] .text-muted { color: #a8a49e !important; }
        [data-ogsc] .email-link { color: #c8c4be !important; }
        [data-ogsc] .divider-line { border-color: #3a3835 !important; }
        [data-ogsc] .footer-bg { background-color: #1a1a18 !important; }
        [data-ogsc] .btn-primary { background-color: #e0ddd8 !important; color: #1a1a18 !important; }
        [data-ogsc] .btn-secondary { color: #e0ddd8 !important; border-color: #e0ddd8 !important; }
        [data-ogsc] .avatar-name-dm { color: #ece9e4 !important; }
        [data-ogsc] .avatar-subtitle-dm { color: #a8a49e !important; }
        [data-ogsc] .stat-card-dm { background-color: #2a2927 !important; }
        [data-ogsc] .stat-label-dm { color: #a8a49e !important; }
        [data-ogsc] .timeline-border-dm { border-color: #3a3835 !important; }
        [data-ogsc] .timeline-text-dm { color: #e0ddd8 !important; }
        [data-ogsc] .timeline-time-dm { color: #a8a49e !important; }
        [data-ogsc] .bar-chart-dm { background-color: #2a2927 !important; }
        [data-ogsc] .bar-track-dm { background-color: #1a1a18 !important; }
        [data-ogsc] .bar-label-dm { color: #a8a49e !important; }
        [data-ogsc] .contributor-card-dm { background-color: #2a2927 !important; }
        [data-ogsc] .contributor-meta-dm { color: #a8a49e !important; }
        [data-ogsc] .callout-critical-dm { background-color: #2a2220 !important; }
        [data-ogsc] .callout-positive-dm { background-color: #202a22 !important; }
        [data-ogsc] .callout-info-dm { background-color: #20242a !important; }
        .tfix { width:100% !important; table-layout:fixed !important; }
    </style>
</head>"""

_OPEN_BODY = """<body style="margin:0; padding:0; background-color:#f5f3f1; width:100%; -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%;" class="body-bg">

    <!-- Preheader text (hidden) -->
    <div style="display:none; font-size:1px; color:#f5f3f1; line-height:1px; max-height:0px; max-width:0px; opacity:0; overflow:hidden; mso-hide:all;" class="preheader-bg">
        __PREHEADER__
        &zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;
    </div>

    <!-- Outer background table -->
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color:#f5f3f1;" class="body-bg">
    <tr>
    <td align="center" valign="top" style="padding:20px 10px;">

        <!-- Ghost table for Outlook -->
        <!--[if mso]>
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" align="center">
        <tr>
        <td>
        <![endif]-->

        <!-- Email container -->
        <div style="max-width:600px; width:100%; margin:0 auto;" class="email-container">


"""

_CLOSE_BODY = """        </div>
        <!-- /Email container -->

        <!--[if mso]>
        </td>
        </tr>
        </table>
        <![endif]-->

    </td>
    </tr>
    </table>
    <!-- /Outer background table -->

</body>
</html>
"""


def _text(value: object) -> str:
    return escape(str(value), quote=True)


def head(title: str) -> str:
    """Return the XHTML declaration, namespaces, and complete template head."""
    return _HEAD.replace("__TITLE__", _text(title), 1)


def open_body(preheader: str) -> str:
    """Open the background, Outlook ghost table, and 600px email container."""
    return _OPEN_BODY.replace("__PREHEADER__", _text(preheader), 1)


def close_body() -> str:
    """Close the email container, Outlook ghost table, background, and HTML."""
    return _CLOSE_BODY


def section_open() -> str:
    """Open a full-width section; append cell() rows and section_close()."""
    return (
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0" '
        'width="100%" style="background-color:#f5f3f1;" class="email-body-bg tfix">\n'
    )


def section_close() -> str:
    return '</table>\n'


def cell(inner: str, pad: str = "16px 40px 0 40px") -> str:
    """Wrap trusted inner HTML in one responsive body-cell row."""
    return '<tr><td style="padding:' + _text(pad) + ';" class="body-cell">' + inner + '</td></tr>\n'


def h2(text: str) -> str:
    return (
        '<h2 class="email-h2 heading-dm" style="margin:0; Margin:0; '
        f"font-family:{FONT_HEADING}; font-size:22px; font-weight:700; "
        'line-height:1.3; letter-spacing:-0.015em; color:#222222;">'
        + _text(text) + '</h2>'
    )


def h3(text: str) -> str:
    return (
        '<h3 class="heading-dm" style="margin:0; Margin:0; '
        f"font-family:{FONT_HEADING}; font-size:18px; font-weight:600; "
        'line-height:1.3; color:#222222;">' + _text(text) + '</h3>'
    )


def p(text: str) -> str:
    return (
        '<p style="margin:0; Margin:0; '
        f"font-family:{FONT_BODY}; font-size:16px; line-height:1.6; "
        'letter-spacing:0.01em; color:#222222;" class="text-main">'
        + _text(text) + '</p>'
    )


def lead(text: str) -> str:
    return (
        '<p style="margin:0; Margin:0; '
        f"font-family:{FONT_BODY}; font-size:18px; line-height:1.55; "
        'color:#555555;" class="text-muted">' + _text(text) + '</p>'
    )


def small(text: str) -> str:
    return (
        '<p style="margin:0; Margin:0; '
        f"font-family:{FONT_BODY}; font-size:13px; line-height:1.5; "
        'color:#666666;" class="text-muted">' + _text(text) + '</p>'
    )


# Preserve the public masthead keyword "lead" without shadowing the helper.
_lead_paragraph = lead


def masthead(
    eyebrow: str, title: str, lead: Optional[str] = None,
    caption: Optional[str] = None,
) -> str:
    """Return the template header section with its 2px bottom rule."""
    parts = [section_open(), (
        '<tr><td style="padding:40px 40px 10px 40px; text-align:left;" class="body-cell">'
        '<p style="margin:0; Margin:0; '
        f"font-family:{FONT_HEADING}; font-size:12px; font-weight:600; "
        'letter-spacing:0.08em; text-transform:uppercase; color:#555555;" '
        'class="text-muted heading-dm">' + _text(eyebrow) + '</p></td></tr>\n'
    ), cell(
        '<h1 class="email-h1 heading-dm text-main" style="margin:0; Margin:0; '
        f"font-family:{FONT_HEADING}; font-size:30px; font-weight:700; "
        'line-height:1.1; letter-spacing:-0.02em; color:#222222;">'
        + _text(title) + '</h1>', "10px 40px 0 40px"
    )]
    if lead is not None:
        parts.append(cell(_lead_paragraph(lead)))
    if caption is not None:
        parts.append(cell(small(caption), "12px 40px 0 40px"))
    parts.extend([cell(
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">'
        '<tr><td style="border-top:2px solid #222222; font-size:1px; line-height:1px; '
        'mso-line-height-rule:exactly;" class="header-border">&nbsp;</td></tr></table>',
        "24px 40px 0 40px"
    ), section_close()])
    return ''.join(parts)


def table(
    headers: Sequence[str], rows: Iterable[Sequence[object]],
    aligns: Optional[Sequence[str]] = None, striped: bool = True,
    widths: Optional[Sequence[Union[str, int]]] = None,
) -> str:
    """Return a table of escaped text; widths use HTML width attributes."""
    count = len(headers)
    if not count:
        raise ValueError("table requires at least one header")
    alignment = list(aligns) if aligns is not None else ["left"] * count
    if len(alignment) != count or any(a not in ("left", "center", "right") for a in alignment):
        raise ValueError("aligns must contain one left/center/right value per header")
    if widths is not None and len(widths) != count:
        raise ValueError("widths must contain one value per header")
    parts = [
        '<table cellspacing="0" cellpadding="0" border="0" width="100%" '
        f'style="font-family:{FONT_BODY}; font-size:14px; line-height:1.5; '
        'color:#222222; border-collapse:collapse;" class="text-main tfix">\n<tr>'
    ]
    for index, heading in enumerate(headers):
        width = ' width="' + _text(widths[index]) + '"' if widths is not None else ''
        parts.append(
            '<th align="' + _text(alignment[index]) + '"' + width
            + ' style="padding:10px 12px; '
            f"font-family:{FONT_HEADING}; font-weight:600; font-size:13px; "
            'text-transform:uppercase; letter-spacing:0.03em; border-bottom:2px solid #222222; '
            'color:#222222;" class="heading-dm header-border">' + _text(heading) + '</th>'
        )
    parts.append('</tr>\n')
    for row_index, row in enumerate(rows):
        if len(row) != count:
            raise ValueError("each row must contain one cell per header")
        parts.append(
            '<tr style="background-color:#ece9e6;" class="table-stripe">'
            if striped and row_index % 2 == 0 else '<tr>'
        )
        for index, value in enumerate(row):
            style = 'padding:10px 12px;' if striped else 'padding:10px 12px; border-bottom:1px solid #dddddd;'
            hook = '' if striped else ' class="divider-line"'
            parts.append(
                '<td align="' + _text(alignment[index]) + '" style="' + style + '"'
                + hook + '>' + _text(value) + '</td>'
            )
        parts.append('</tr>\n')
    parts.append('</table>')
    return ''.join(parts)


def stat_grid(stats: Iterable[Tuple[object, str, str]]) -> str:
    """Return inner markup with at most four template stat columns per row."""
    values = list(stats)
    if not values:
        return ''
    parts: List[str] = []
    for start in range(0, len(values), 4):
        row = values[start:start + 4]
        parts.append(
            '<div style="font-size:0; text-align:center;">\n'
            '<!--[if mso]>\n'
            '<table role="presentation" cellspacing="0" cellpadding="0" border="0" '
            f'width="{130 * len(row)}" align="center">\n<tr>\n<![endif]-->\n'
        )
        for value, label, color in row:
            parts.append(
                '<!--[if mso]>\n<td valign="top" width="130" align="center">\n<![endif]-->\n'
                '<div style="display:inline-block; width:100%; max-width:130px; vertical-align:top; '
                'text-align:center;" class="stat-col">'
                '<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">'
                '<tr><td align="center" style="padding:4px;">'
                '<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">'
                '<tr><td bgcolor="#fefefe" style="background-color:#fefefe; padding:16px 12px; '
                'text-align:center;" class="stat-card-dm">'
                '<p style="margin:0; Margin:0; '
                f"font-family:{FONT_HEADING}; font-size:32px; font-weight:700; line-height:1.1; "
                'color:' + _text(color) + ';" class="stat-value heading-dm">' + _text(value) + '</p>'
                '<p style="margin:4px 0 0 0; Margin:4px 0 0 0; '
                f"font-family:{FONT_HEADING}; font-size:11px; font-weight:600; "
                'text-transform:uppercase; letter-spacing:0.04em; color:#777777;" '
                'class="stat-label-dm">' + _text(label) + '</p>'
                '</td></tr></table></td></tr></table></div>\n'
                '<!--[if mso]>\n</td>\n<![endif]-->\n'
            )
        parts.append('<!--[if mso]>\n</tr>\n</table>\n<![endif]-->\n</div>\n')
    return ''.join(parts)


def badge(text: str, variant: str = "default") -> str:
    """Return a default, outline, or muted template badge."""
    variants = {
        "default": ('padding:5px 10px; border-radius:12px; background-color:#e8e6e3; color:#222222; '
                    'text-transform:uppercase; letter-spacing:0.03em;', 'badge-bg'),
        "outline": ('padding:4px 9px; border-radius:12px; background-color:transparent; color:#222222; '
                    'text-transform:uppercase; letter-spacing:0.03em; border:1px solid #888888;', 'badge-outline'),
        "muted": ('padding:5px 10px; border-radius:12px; background-color:#dddad7; color:#555555; '
                  'text-transform:uppercase; letter-spacing:0.03em;', 'badge-bg text-muted'),
    }
    if variant not in variants:
        raise ValueError("badge variant must be default, outline, or muted")
    style, hook = variants[variant]
    return (
        '<span style="display:inline-block; '
        f"font-family:{FONT_HEADING}; font-size:11px; font-weight:600; line-height:1; "
        + style + '" class="' + hook + '">' + _text(text) + '</span>'
    )


def callout(kind: str, title: str, body: str) -> str:
    """Return one of the five template callouts with escaped title and body."""
    variants = {
        "note": (INK, STRIPE, INK, "callout-info-bg"),
        "warning": (AMBER, "#faf3e6", "#8a6520", "callout-warning-bg"),
        "critical": (RED, "#fdf0ee", RED, "callout-critical-dm"),
        "positive": (GREEN, "#f0f8f2", GREEN, "callout-positive-dm"),
        "info": (BLUE, "#eef5fb", BLUE, "callout-info-dm"),
    }
    if kind not in variants:
        raise ValueError("callout kind must be note, warning, critical, positive, or info")
    border, background, title_color, hook = variants[kind]
    basic = kind in ("note", "warning")
    table_attr = ' class="' + hook + '"' if basic else (
        ' style="margin-bottom:16px;"' if kind in ("critical", "positive") else ''
    )
    border_hook = ' class="callout-info-border"' if kind == "note" else ''
    weight, spacing, line_height = (600, "0.03em", "1.6") if basic else (700, "0.04em", "1.55")
    return (
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%"'
        + table_attr + '><tr>'
        f'<td width="4" bgcolor="{border}" style="background-color:{border};"'
        + border_hook + '></td>'
        f'<td bgcolor="{background}" style="background-color:{background}; padding:16px 20px;" '
        f'class="{hook}">'
        '<p style="margin:0; Margin:0 0 4px 0; '
        f"font-family:{FONT_HEADING}; font-size:13px; font-weight:{weight}; "
        f'text-transform:uppercase; letter-spacing:{spacing}; color:{title_color};" '
        'class="heading-dm">' + _text(title) + '</p>'
        '<p style="margin:0; Margin:0; '
        f'font-family:{FONT_BODY}; font-size:15px; line-height:{line_height}; color:#222222;" '
        'class="text-main">' + _text(body) + '</p></td></tr></table>'
    )


def button(label: str, href: str, secondary: bool = False) -> str:
    """Return a primary or secondary table-backed action button."""
    td = (
        '<td style="border-radius:6px;" class="btn-secondary">' if secondary else
        '<td style="border-radius:6px; background-color:#222222;" bgcolor="#222222" class="btn-primary">'
    )
    hook = 'btn-secondary' if secondary else 'btn-primary'
    color = INK if secondary else BG
    background = ' background-color:transparent;' if secondary else ''
    return (
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0"><tr>' + td
        + '<a href="' + _text(href) + '" style="display:inline-block; padding:12px 28px; '
        f"font-family:{FONT_HEADING}; font-size:15px; font-weight:600; line-height:1.2; "
        f'color:{color}; text-decoration:none; border-radius:6px; border:2px solid #222222;'
        + background + '" class="' + hook + '">' + _text(label) + '</a></td></tr></table>'
    )


def divider() -> str:
    return (
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">'
        '<tr><td style="border-top:1px solid #dddddd; font-size:1px; line-height:1px; '
        'mso-line-height-rule:exactly;" class="divider-line">&nbsp;</td></tr></table>'
    )


def spacer() -> str:
    """Return the template's 40px section spacer before the footer."""
    return (
        section_open() + '<tr><td style="padding:40px 0 0 0; font-size:1px; '
        'line-height:1px; mso-line-height-rule:exactly;">&nbsp;</td></tr>' + section_close()
    )


def footer(
    title: str, lines: Sequence[str], links: Iterable[Tuple[str, str]] = (),
) -> str:
    """Return a footer; the final line is metadata and links are (label, URL)."""
    parts = [
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">'
        '<tr><td bgcolor="#ece9e6" style="background-color:#ece9e6; padding:32px 40px; '
        'border-radius:0 0 6px 6px;" class="footer-bg body-cell">'
        '<p style="margin:0; Margin:0 0 8px 0; '
        f"font-family:{FONT_HEADING}; font-size:13px; font-weight:600; color:#222222; "
        'text-align:center;" class="heading-dm">' + _text(title) + '</p>'
    ]
    if len(lines) > 1:
        parts.append(
            '<p style="margin:0; Margin:0 0 16px 0; '
            f"font-family:{FONT_BODY}; font-size:12px; line-height:1.5; color:#555555; "
            'text-align:center;" class="text-muted">'
            + '<br />'.join(_text(line) for line in lines[:-1]) + '</p>'
        )
    rendered_links = [
        '<a href="' + _text(href) + '" style="color:#555555; text-decoration:underline;" '
        'class="email-link">' + _text(label) + '</a>' for label, href in links
    ]
    if rendered_links:
        parts.append(
            '<p style="margin:0; Margin:0 0 8px 0; '
            f"font-family:{FONT_BODY}; font-size:12px; line-height:1.5; color:#555555; "
            'text-align:center;" class="text-muted">'
            + ' &nbsp;&middot;&nbsp; '.join(rendered_links) + '</p>'
        )
    if lines:
        parts.append(
            '<p style="margin:0; Margin:0; '
            f"font-family:{FONT_BODY}; font-size:11px; line-height:1.4; color:#888888; "
            'text-align:center;" class="text-muted">' + _text(lines[-1]) + '</p>'
        )
    parts.append('</td></tr></table>\n')
    return ''.join(parts)


def document(title: str, preheader: str, body_html: str, footer_html: str) -> str:
    """Join trusted complete sections with the email head and body envelope."""
    return head(title) + '\n\n' + open_body(preheader) + body_html + footer_html + close_body()


def _demo() -> str:
    body = masthead(
        "Daily digest", "A shared email language",
        lead="A sample of every component in the canonical digest shell.",
        caption="Wednesday, October 21, 2026 · PT edition",
    )
    body += section_open()
    body += cell(h2("Today at a glance"), "32px 40px 0 40px")
    body += cell(stat_grid([
        ("16", "Started", RED), ("12", "Completed", GREEN),
        ("3", "Pending", AMBER), ("75%", "Success rate", BLUE),
        ("1", "Follow-up", INK),
    ]))
    body += cell(h3("The daily picture"))
    body += cell(lead("A consistent hierarchy makes each report easy to scan."))
    body += cell(p('Text is escaped safely: <example> & "quoted text" stay readable.'))
    body += cell(small("The report includes the current edition and data window."))
    body += cell(divider(), "20px 40px 0 40px")
    body += cell(h2("Tables and status"), "32px 40px 0 40px")
    body += cell(table(
        ["Product", "Purchases", "Revenue"],
        [["MarineRadar", 3, "$412"], ["TravelAnimator", 7, "$560"], ["Measure", 2, "$98"]],
        aligns=["left", "right", "right"], widths=["50%", "25%", "25%"],
    ))
    body += cell(table(["Edition", "Local delivery"], [["PT", "05:55"], ["IST", "05:55"]], striped=False))
    body += cell(' &nbsp; '.join(badge(name, name) for name in ("default", "outline", "muted")))
    body += cell(h2("Context and next steps"), "32px 40px 0 40px")
    for kind, title, text in [
        ("note", "Note", "The same shell supports every digest."),
        ("warning", "Warning", "A late source can delay the current report."),
        ("critical", "Critical", "A failed delivery requires investigation."),
        ("positive", "Positive", "Today's completed exports are ready to view."),
        ("info", "Info", "Each edition follows its own local report date."),
    ]:
        body += cell(callout(kind, title, text))
    body += cell(button("Open the report", "https://example.com/report?edition=pt&demo=1"))
    body += cell(button("View source", "https://example.com/source", secondary=True))
    body += section_close() + spacer()
    return document(
        "Digest shell · component demo", "Metrics, updates, and context for your morning.", body,
        footer("Lascade daily digests", ["A local component preview.", "© 2026 Lascade"],
               [("View in browser", "https://example.com/report"), ("Preferences", "https://example.com/preferences")]),
    )


if __name__ == "__main__":
    import sys
    from pathlib import Path

    if len(sys.argv) != 2:
        raise SystemExit('Usage: python3 "Style Template/email_shell.py" <output.html>')
    Path(sys.argv[1]).write_text(_demo(), encoding="utf-8")
