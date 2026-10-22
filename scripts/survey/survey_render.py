#!/usr/bin/env python3
"""Pure product-agnostic survey renderer built on the shared email shell."""
from html import escape
from math import ceil
import re

from scripts.common import email_shell as shell


def _distribution(options):
    """Compose horizontal bars from escaped labels and the template palette."""
    rows = []
    for index, option in enumerate(options):
        pct = max(0.0, min(100.0, float(option["pct"])))
        width = max(pct, 2.0)
        color = escape(str(option.get("color", shell.BLUE)), quote=True)
        stripe = (f' style="background-color:{shell.STRIPE};" class="table-stripe"'
                  if index % 2 == 0 else '')
        rows.append(
            f'<tr{stripe}><td width="42%" style="padding:10px 12px;">'
            + escape(str(option["value"]))
            + '</td><td width="33%" style="padding:10px 6px;">'
            '<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%"><tr>'
            f'<td width="{width:g}%" bgcolor="{color}" style="background-color:{color}; '
            'height:8px; font-size:1px; line-height:1px;">&nbsp;</td>'
            f'<td width="{100 - width:g}%" style="font-size:1px; line-height:1px;">&nbsp;</td>'
            '</tr></table></td><td width="25%" align="right" '
            f'style="padding:10px 12px; white-space:nowrap;">{pct:.0f}% '
            f'({escape(str(option["count"]))})</td></tr>'
        )
    return (
        '<table cellspacing="0" cellpadding="0" border="0" width="100%" '
        f'style="font-family:{shell.FONT_BODY}; font-size:14px; line-height:1.5; '
        f'color:{shell.INK};" class="text-main tfix">' + ''.join(rows) + '</table>'
    )


def _summary(summary):
    body = shell.cell(shell.h3(summary["header"]), "24px 40px 0 40px")
    kind = summary["type"]
    if kind == "distribution":
        body += shell.cell(_distribution(summary["options"]), "12px 40px 0 40px")
    elif kind == "score":
        average = summary["avg"]
        color = shell.GREEN if average >= 4 else shell.AMBER if average >= 3 else shell.RED
        body += shell.cell(shell.stat_grid([
            (f"{average}/5", f"Average · {summary['total']} responses", color)
        ]))
    elif kind == "grouped":
        groups = summary["groups"]
        if groups:
            table = shell.table(
                ["Response theme", "Count"],
                [[group["text"], group["count"]] for group in groups],
                aligns=["left", "right"], widths=["", "72"],
            ).replace(' width=""', '', 1)
            body += shell.cell(table)
        else:
            body += shell.cell(shell.small("No meaningful responses"), "8px 40px 0 40px")
    return body


def _response_widths(headers):
    """Budget 333px for whole header words, then expand free-text columns."""
    # Round minimum shares up to hundredths of a percent so formatting never
    # takes width away from a header. Inter uppercase is estimated at 9.5px.
    shares = [ceil((max((len(word) for word in str(header).upper().split()), default=0)
                    * 9.5 + 24) * 10000 / 333) for header in headers]
    choice_headers = {"status", "score", "frequency", "got measurement?"}
    text_columns = [index for index, header in enumerate(headers)
                    if str(header).strip().lower() not in choice_headers]
    recipients = text_columns or list(range(len(headers)))
    extra, remainder = divmod(max(0, 10000 - sum(shares)), len(recipients))
    for offset, index in enumerate(recipients):
        shares[index] += extra + (offset < remainder)
    return [f"{share / 100:.2f}%" for share in shares]


def _response_table(section):
    headers = (["Status"] if section["has_status"] else []) + list(section["columns"])
    rows = []
    for response in section["rows"]:
        status = [response.get("status_label") or "Free"] if section["has_status"] else []
        rows.append(status + [cell["value"] for cell in response["cells"]])
    if len(headers) < 4:
        widths = _response_widths(headers) if len(headers) in (2, 3) else None
        return shell.table(headers, rows, widths=widths)

    records = []
    for row in rows:
        fields = [(str(header), str(value).strip())
                  for header, value in zip(headers, row) if value is not None]
        fields = [(header, value) for header, value in fields if value and value != "—"]
        primary = fields[0][1] if fields else ''
        if fields and (row[0] is None or str(row[0]).strip() in ('', '—')):
            header = fields[0][0]
            primary = header + (' ' if header == 'IMO' else ': ') + primary
        record = '<strong>' + escape(primary) + '</strong>' if fields else ''
        if len(fields) > 1:
            caption = ' · '.join(
                header + (' ' if header == 'IMO' else ': ') + value
                for header, value in fields[1:]
            )
            record += (
                '<br /><span style="font-size:13px; line-height:1.5; color:#666666;" '
                'class="text-muted">' + escape(caption) + '</span>'
            )
        records.append(record)

    # The shell accepts text-only cells. Fill only its generated empty cells
    # with trusted markup whose external field values are already escaped.
    table = shell.table([headers[0]], [[""] for _ in records])
    record_html = iter(records)
    return re.sub(r'(<td\b[^>]*>)(</td>)',
                  lambda match: match[1] + next(record_html) + match[2], table)


def render(model):
    """Return the metric tail and HTML body; the caller composes the subject."""
    m = model
    total = m["total"]
    survey_count = m.get("survey_count", len(m["sections"]))
    tail = f"{total} new response{'s' if total != 1 else ''}"
    preheader = f"{tail} from {survey_count} survey{'s' if survey_count != 1 else ''}"
    body = shell.masthead(
        "Daily survey digest", m["email_title"], lead=m["date_str"],
        caption=f"{preheader} · Since {m['cutoff_str']}",
    )
    body += shell.section_open()
    if not m["sections"]:
        body += shell.cell(shell.small("No new survey responses in this reporting window."), "24px 40px 0 40px")
    for section in m["sections"]:
        body += shell.cell(shell.h2(section["label"]), "32px 40px 0 40px")
        count = section["count"]
        caption = " · ".join(part for part in (
            section.get("subtitle", ""), f"{count} response{'s' if count != 1 else ''}"
        ) if part)
        body += shell.cell(shell.small(caption), "8px 40px 0 40px")
        mode = section.get("render", "table")
        if mode == "distribution":
            for distribution in section["distributions"]:
                body += shell.cell(shell.h3(distribution["header"]), "24px 40px 0 40px")
                body += shell.cell(_distribution(distribution["options"]), "12px 40px 0 40px")
        elif mode == "summary":
            body += ''.join(_summary(summary) for summary in section["summaries"])
        else:
            body += shell.cell(_response_table(section))
    body += shell.cell(shell.button("View all in Sheets", m["sheet_url"]), "32px 40px 0 40px")
    body += shell.section_close() + shell.spacer()
    return tail, shell.document(
        m["email_title"], preheader, body,
        shell.footer(f"{m['product_name']} survey digest", ["Sent automatically by Lascade"]),
    )
