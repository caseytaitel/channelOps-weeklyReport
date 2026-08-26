"""HTML rendering for the weekly Channel Ops report."""

import html
from datetime import datetime

from report_config import (
    DEAL_RECORD_URL,
    DEAL_REG_SURFACE_DAYS,
    MEETINGS_VIEW_URL,
    RESELLERS_VIEW_URL,
    STALLED_THRESHOLD_DAYS,
)

# Urgency bands for days-since-approval / days-in-stage highlighting.
# Under 30 is uncolored. Yellow = 30–59, orange = 60–89, red = 90+.
URGENCY_MILD = 30
URGENCY_WARN = 60
URGENCY_CRITICAL = 90


def _esc(value):
    return html.escape("" if value is None else str(value))


def _deal_href(deal_id):
    return DEAL_RECORD_URL.format(deal_id=deal_id)


def _urgency_class(days):
    if days is None:
        return ""
    if days >= URGENCY_CRITICAL:
        return "row-critical"
    if days >= URGENCY_WARN:
        return "row-warn"
    if days >= URGENCY_MILD:
        return "row-mild"
    return ""


def _days_badge(days):
    if days is None:
        return '<span class="badge badge-unknown">—</span>'
    cls = _urgency_class(days)
    if not cls:
        return f"<span>{days}</span>"
    badge = {
        "row-critical": "badge-critical",
        "row-warn": "badge-warn",
        "row-mild": "badge-mild",
    }[cls]
    return f'<span class="badge {badge}">{days}</span>'


def _format_date(date_str):
    if not date_str:
        return "—"
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").strftime("%b %d, %Y")
    except ValueError:
        return date_str


def _deal_name_cell(deal_id, name):
    return (
        f'<a class="deal-link" href="{_esc(_deal_href(deal_id))}" '
        f'target="_blank" rel="noopener">{_esc(name)}</a>'
    )


def _empty_row(colspan, message):
    return f'<tr class="empty"><td colspan="{colspan}">{_esc(message)}</td></tr>'


def _table_body(rows, days_key, empty_colspan, empty_message, cells_fn):
    if not rows:
        return _empty_row(empty_colspan, empty_message)
    parts = []
    for r in rows:
        days = r[days_key]
        parts.append(f'<tr class="{_urgency_class(days)}">{cells_fn(r, days)}</tr>')
    return "\n".join(parts)


def _deal_reg_rows(rows):
    return _table_body(
        rows,
        days_key="days_since_approval",
        empty_colspan=5,
        empty_message=(
            f"None currently — no Approved deal regs more than "
            f"{DEAL_REG_SURFACE_DAYS} days since approval."
        ),
        cells_fn=lambda r, days: (
            f"<td>{_deal_name_cell(r['id'], r['name'])}</td>"
            f"<td class=\"num\">{_days_badge(days)}</td>"
            f"<td>{_esc(r['owner'])}</td>"
            f"<td>{_esc(r['partner'])}</td>"
            f"<td>{_esc(r['partner_email'])}</td>"
        ),
    )


def _stalled_rows(rows):
    return _table_body(
        rows,
        days_key="days_in_stage",
        empty_colspan=8,
        empty_message=(
            f"None currently — no other open Channel deals more than "
            f"{STALLED_THRESHOLD_DAYS} days in stage."
        ),
        cells_fn=lambda r, days: (
            f"<td>{_deal_name_cell(r['id'], r['name'])}</td>"
            f"<td>{_esc(r['stage_label'])}</td>"
            f"<td class=\"num\">{_days_badge(days)}</td>"
            f"<td class=\"nowrap\">{_esc(_format_date(r['close_date']))}</td>"
            f"<td>{_esc(r['owner'])}</td>"
            f"<td>{_esc(r['channel_deal_type'])}</td>"
            f"<td>{_esc(r['partner'])}</td>"
            f"<td>{_esc(r['partner_email'])}</td>"
        ),
    )


def _stalled_table(rows):
    return (
        '<div class="table-wrap">\n'
        "        <table>\n"
        "          <thead>\n"
        "            <tr>\n"
        "              <th>Deal Name</th>\n"
        "              <th>Stage</th>\n"
        "              <th>Days in Stage</th>\n"
        "              <th>Close Date</th>\n"
        "              <th>Owner</th>\n"
        "              <th>Channel Deal Type</th>\n"
        "              <th>Channel Partner</th>\n"
        "              <th>Partner Contact Email</th>\n"
        "            </tr>\n"
        "          </thead>\n"
        "          <tbody>\n"
        f"            {_stalled_rows(rows)}\n"
        "          </tbody>\n"
        "        </table>\n"
        "      </div>"
    )


def _urgency_legend():
    """Same cutoffs that color the days badges on Unqualified and Stalled."""
    return (
        f'<div class="legend" aria-label="Color bands">'
        f'<span class="badge badge-mild">{URGENCY_MILD}–{URGENCY_WARN - 1}d</span>'
        f'<span class="badge badge-warn">{URGENCY_WARN}–{URGENCY_CRITICAL - 1}d</span>'
        f'<span class="badge badge-critical">{URGENCY_CRITICAL}d+</span>'
        f"</div>"
    )


def _stalled_sections_html(sections):
    if not sections:
        return _stalled_table([])
    parts = []
    for label, rows in sections:
        parts.append(
            f'<div class="section">\n'
            f"      <h2>{_esc(label)}</h2>\n"
            f"      {_stalled_table(rows)}\n"
            f"    </div>"
        )
    return "\n    ".join(parts)


def build_html_report(report, now):
    """Return a complete, self-contained HTML document for the weekly RevOps report."""
    today = now.strftime("%B %d, %Y")
    channel_count = report["channel_count"]
    deal_reg_count = report["deal_reg_count"]
    qualified_count = report["qualified_count"]
    deal_reg_rows = report["unqualified_deal_regs"]
    stalled = report["stalled"]
    stalled_sections = report["stalled_sections"]
    unqualified_count = len(deal_reg_rows)
    stalled_count = len(stalled)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Weekly Channel Update — {today}</title>
<style>
  :root {{
    --bg: #f4f6f8;
    --card: #ffffff;
    --ink: #1c2430;
    --muted: #5c6b7a;
    --line: #e4e8ed;
    --accent: #1f6feb;
    --mild: #a16207;
    --mild-bg: #fff7d9;
    --warn: #9a3412;
    --warn-bg: #fff1e6;
    --crit: #9f1239;
    --crit-bg: #fff1f2;
    --ok: #166534;
    --callout: #eef4ff;
    --callout-bar: #1f6feb;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--bg);
    color: var(--ink);
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
    font-size: 14px;
    line-height: 1.45;
  }}
  .page {{
    max-width: 1120px;
    margin: 0 auto;
    padding: 28px 20px 48px;
  }}
  .masthead {{
    padding: 4px 0 16px;
  }}
  .masthead h1 {{
    margin: 0 0 4px;
    font-size: 20px;
    font-weight: 600;
    color: var(--ink);
  }}
  .masthead .date {{
    margin: 0;
    color: var(--muted);
    font-size: 13px;
  }}
  .tab-radio {{
    position: absolute;
    opacity: 0;
    pointer-events: none;
  }}
  .tabs {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px 0;
    border-bottom: 1px solid var(--line);
    margin-bottom: 22px;
  }}
  .tabs label {{
    padding: 10px 16px 11px;
    margin-bottom: -1px;
    cursor: pointer;
    color: var(--muted);
    font-weight: 600;
    font-size: 13px;
    border-bottom: 2px solid transparent;
  }}
  .tabs .count {{
    display: inline-block;
    min-width: 1.4em;
    margin-left: 6px;
    padding: 0 6px;
    border-radius: 999px;
    background: #eef2f6;
    color: var(--muted);
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    text-align: center;
  }}
  #tab-overview:checked ~ .tabs label[for="tab-overview"],
  #tab-dealregs:checked ~ .tabs label[for="tab-dealregs"],
  #tab-stalled:checked ~ .tabs label[for="tab-stalled"] {{
    color: var(--ink);
    border-bottom-color: var(--accent);
  }}
  #tab-dealregs:checked ~ .tabs label[for="tab-dealregs"] .count,
  #tab-stalled:checked ~ .tabs label[for="tab-stalled"] .count {{
    background: #e8f0fe;
    color: var(--accent);
  }}
  #tab-dealregs:checked ~ .tabs .legend,
  #tab-stalled:checked ~ .tabs .legend {{
    display: flex;
  }}
  .panel {{ display: none; }}
  #tab-overview:checked ~ .panel-overview,
  #tab-dealregs:checked ~ .panel-dealregs,
  #tab-stalled:checked ~ .panel-stalled {{
    display: block;
  }}
  .summary {{
    padding: 0 0 18px;
    margin-bottom: 22px;
  }}
  .stats {{
    display: flex;
    flex-direction: column;
    gap: 16px;
  }}
  .stat-group {{
    display: flex;
    flex-direction: column;
    gap: 5px;
  }}
  .stat-children {{
    display: flex;
    flex-direction: column;
    gap: 5px;
    margin-left: 0.35em;
    padding-left: 14px;
    border-left: 2px solid var(--line);
  }}
  .stat-line {{
    display: block;
    margin: 0;
    font-size: 14px;
    font-weight: 400;
    color: var(--ink);
  }}
  .stat-num {{
    display: inline-block;
    min-width: 2ch;
    font-weight: 600;
    font-size: 15px;
    font-variant-numeric: tabular-nums;
    text-align: right;
  }}
  .stat-flag {{ color: var(--warn); }}
  .stat-ok {{ color: var(--ok); }}
  .stat-detail {{
    color: var(--muted);
    font-weight: 400;
  }}
  .stat-jump {{
    cursor: pointer;
    border: 0;
    background: none;
    padding: 0;
    font: inherit;
    text-align: left;
    color: inherit;
  }}
  .stat-jump:hover .stat-detail {{
    color: var(--accent);
  }}
  h2 {{
    margin: 0 0 10px;
    font-size: 15px;
    font-weight: 600;
    letter-spacing: 0.01em;
  }}
  .section {{ margin-bottom: 26px; }}
  .table-wrap {{
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    overflow: auto;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }}
  th, td {{
    padding: 8px 12px;
    text-align: left;
    vertical-align: top;
    border-bottom: 1px solid var(--line);
  }}
  th {{
    background: #f7f9fb;
    color: #3d4d5c;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    white-space: nowrap;
    position: sticky;
    top: 0;
  }}
  tr:last-child td {{ border-bottom: none; }}
  tbody tr:hover td {{ background: #fafbfd; }}
  tbody tr.row-mild:hover td {{ background: #feeda9; }}
  tbody tr.row-warn:hover td {{ background: #ffe4cc; }}
  tbody tr.row-critical:hover td {{ background: #ffe4e6; }}
  .num {{ white-space: nowrap; }}
  .nowrap {{ white-space: nowrap; }}
  .deal-link {{
    color: var(--accent);
    text-decoration: none;
    font-weight: 600;
  }}
  .deal-link:hover {{ text-decoration: underline; }}
  tr.row-mild {{ background: var(--mild-bg); }}
  tr.row-warn {{ background: var(--warn-bg); }}
  tr.row-critical {{ background: var(--crit-bg); }}
  tr.empty td {{
    color: var(--muted);
    font-style: italic;
    padding: 16px 12px;
  }}
  .badge {{
    display: inline-block;
    min-width: 2.6em;
    padding: 1px 7px;
    border-radius: 999px;
    font-variant-numeric: tabular-nums;
    font-weight: 600;
    font-size: 12px;
    text-align: center;
  }}
  .badge-mild {{ background: #feeda9; color: var(--mild); }}
  .badge-warn {{ background: #fed7aa; color: var(--warn); }}
  .badge-critical {{ background: #ffe4e6; color: var(--crit); }}
  .badge-unknown {{ background: #f1f5f9; color: var(--muted); }}
  .legend {{
    display: none;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-left: auto;
    padding: 0 0 2px;
  }}
  .callouts {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
  }}
  @media (max-width: 720px) {{
    .callouts {{ grid-template-columns: 1fr; }}
  }}
  .callout {{
    background: var(--callout);
    border-radius: 10px;
    padding: 14px 16px 14px 18px;
    box-shadow: inset 4px 0 0 var(--callout-bar);
  }}
  .callout h2 {{ margin-bottom: 6px; }}
  .callout p {{ margin: 0; color: #334155; }}
  .callout a {{ color: var(--accent); font-weight: 600; text-decoration: none; }}
  .callout a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
  <div class="page">
    <header class="masthead">
      <h1>Weekly Channel Update</h1>
      <p class="date">{today}</p>
    </header>

    <input class="tab-radio" type="radio" name="report-tab" id="tab-overview" checked>
    <input class="tab-radio" type="radio" name="report-tab" id="tab-dealregs">
    <input class="tab-radio" type="radio" name="report-tab" id="tab-stalled">

    <nav class="tabs" aria-label="Report sections">
      <label for="tab-overview">Overview</label>
      <label for="tab-dealregs">Unqualified Deal Regs <span class="count">{unqualified_count}</span></label>
      <label for="tab-stalled">Stalled Deals <span class="count">{stalled_count}</span></label>
      {_urgency_legend()}
    </nav>

    <section class="panel panel-overview" aria-labelledby="overview-heading">
      <h2 id="overview-heading" hidden>Overview</h2>
      <div class="summary">
        <div class="stats">
          <p class="stat-line"><span class="stat-num">{channel_count}</span> open Channel Deals</p>
          <div class="stat-group">
            <p class="stat-line"><span class="stat-num">{deal_reg_count}</span> Deal Regs</p>
            <div class="stat-children">
              <p class="stat-line"><span class="stat-num stat-ok">{qualified_count}</span> Qualified</p>
              <label class="stat-line stat-jump" for="tab-dealregs"><span class="stat-num stat-flag">{unqualified_count}</span> Unqualified, review <span class="stat-detail">— more than {DEAL_REG_SURFACE_DAYS} days since approval</span></label>
            </div>
          </div>
          <div class="stat-group">
            <label class="stat-line stat-jump" for="tab-stalled"><span class="stat-num stat-flag">{stalled_count}</span> Stalled, review <span class="stat-detail">— more than {STALLED_THRESHOLD_DAYS} days in stage, any open stage</span></label>
          </div>
        </div>
      </div>
      <div class="callouts">
        <aside class="callout">
          <h2>Resellers Hygiene</h2>
          <p><a href="{_esc(RESELLERS_VIEW_URL)}" target="_blank" rel="noopener">Resellers list</a> — please confirm all current resellers are on this list and accurately marked.</p>
        </aside>
        <aside class="callout">
          <h2>Meeting Hygiene</h2>
          <p><a href="{_esc(MEETINGS_VIEW_URL)}" target="_blank" rel="noopener">Meetings list</a> — please update Call and Meeting Type on these records.</p>
        </aside>
      </div>
    </section>

    <section class="panel panel-dealregs section" aria-label="Unqualified Deal Regs">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Deal Name</th>
              <th>Days Since Approval</th>
              <th>Owner</th>
              <th>Channel Partner</th>
              <th>Partner Contact Email</th>
            </tr>
          </thead>
          <tbody>
            {_deal_reg_rows(deal_reg_rows)}
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel panel-stalled" aria-label="Stalled Deals">
      {_stalled_sections_html(stalled_sections)}
    </section>
  </div>
</body>
</html>
"""
