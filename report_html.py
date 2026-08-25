"""HTML rendering for the weekly Channel Ops report."""

import html
from datetime import datetime

from report_config import (
    DEAL_RECORD_URL,
    MEETINGS_VIEW_URL,
    RESELLERS_VIEW_URL,
    STALLED_THRESHOLD_DAYS,
)

# Urgency bands for days-since-approval / days-in-stage highlighting.
# Watch = 14+, Warn = 30+, Critical = 90+.
URGENCY_WATCH = 14
URGENCY_WARN = 30
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
    if days >= URGENCY_WATCH:
        return "row-watch"
    return ""


def _days_badge(days):
    if days is None:
        return '<span class="badge badge-unknown">—</span>'
    cls = _urgency_class(days) or "row-ok"
    badge = {
        "row-critical": "badge-critical",
        "row-warn": "badge-warn",
        "row-watch": "badge-watch",
        "row-ok": "badge-ok",
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
        empty_message="None currently — all Approved deals are already Qualified.",
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
        empty_message="None currently.",
        cells_fn=lambda r, days: (
            f"<td>{_deal_name_cell(r['id'], r['name'])}</td>"
            f"<td class=\"nowrap\">{_esc(_format_date(r['create_date']))}</td>"
            f"<td class=\"num\">{_days_badge(days)}</td>"
            f"<td>{_esc(r['stage_label'])}</td>"
            f"<td>{_esc(r['owner'])}</td>"
            f"<td>{_esc(r['channel_deal_type'])}</td>"
            f"<td>{_esc(r['partner'])}</td>"
            f"<td>{_esc(r['partner_email'])}</td>"
        ),
    )


def _urgency_legend():
    """Legend labels derived from the same cutoffs that color the rows."""
    return (
        f'<span><i class="dot dot-watch"></i> {URGENCY_WATCH}–{URGENCY_WARN - 1}d</span>\n'
        f'        <span><i class="dot dot-warn"></i> {URGENCY_WARN}–{URGENCY_CRITICAL - 1}d</span>\n'
        f'        <span><i class="dot dot-crit"></i> {URGENCY_CRITICAL}d+</span>'
    )


def build_html_report(deal_reg, stalled, now):
    """Return a complete, self-contained HTML document for the weekly RevOps report."""
    today = now.strftime("%B %d, %Y")
    approved_count = deal_reg["approved_count"]
    qualified_count = deal_reg["qualified_count"]
    deal_reg_total = approved_count + qualified_count
    stalled_count = len(stalled)
    approved_rows = deal_reg["approved_not_qualified"]
    legend = _urgency_legend()

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
    --watch: #c2410c;
    --watch-bg: #fff7ed;
    --watch-bar: #fb923c;
    --warn: #9a3412;
    --warn-bg: #fff1e6;
    --warn-bar: #ea580c;
    --crit: #9f1239;
    --crit-bg: #fff1f2;
    --crit-bar: #e11d48;
    --ok: #166534;
    --ok-bg: #f0fdf4;
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
    border-bottom: 1px solid var(--line);
    padding: 4px 0 16px;
    margin-bottom: 20px;
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
  .summary {{
    border-bottom: 1px solid var(--line);
    padding: 0 0 18px;
    margin-bottom: 22px;
    display: flex;
    flex-wrap: wrap;
    gap: 6px 28px;
    align-items: baseline;
  }}
  .stats {{
    display: flex;
    flex-direction: column;
    gap: 5px;
  }}
  .stat-line {{
    margin: 0;
    font-size: 14px;
    font-weight: 400;
    color: var(--ink);
  }}
  .stat-num {{
    font-weight: 600;
    font-size: 15px;
  }}
  .stat-flag {{ color: var(--warn); }}
  .stat-ok {{ color: var(--ok); }}
  .stat-detail {{
    color: var(--muted);
    font-weight: 400;
  }}
  .legend {{
    margin-left: auto;
    align-self: center;
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    font-size: 12px;
    color: var(--muted);
  }}
  .legend span {{ display: inline-flex; align-items: center; gap: 5px; }}
  .dot {{
    width: 8px; height: 8px; border-radius: 50%; display: inline-block;
  }}
  .dot-watch {{ background: var(--watch-bar); }}
  .dot-warn {{ background: var(--warn-bar); }}
  .dot-crit {{ background: var(--crit-bar); }}
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
  tbody tr.row-watch:hover td {{ background: #ffedd5; }}
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
  tr.row-watch {{ background: var(--watch-bg); }}
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
  .badge-ok {{ background: var(--ok-bg); color: var(--ok); }}
  .badge-watch {{ background: #ffedd5; color: var(--watch); }}
  .badge-warn {{ background: #fed7aa; color: var(--warn); }}
  .badge-critical {{ background: #ffe4e6; color: var(--crit); }}
  .badge-unknown {{ background: #f1f5f9; color: var(--muted); }}
  .callouts {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
  }}
  @media (max-width: 720px) {{
    .callouts {{ grid-template-columns: 1fr; }}
    .legend {{ margin-left: 0; }}
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

    <div class="summary">
      <div class="stats">
        <p class="stat-line"><span class="stat-num stat-ok">{deal_reg_total}</span> deal regs <span class="stat-detail">— {approved_count} approved, {qualified_count} qualified</span></p>
        <p class="stat-line"><span class="stat-num stat-flag">{stalled_count}</span> stalled deals <span class="stat-detail">— more than {STALLED_THRESHOLD_DAYS} days in stage</span></p>
      </div>
      <div class="legend" aria-label="Urgency legend">
        {legend}
      </div>
    </div>

    <section class="section">
      <h2>Deal Regs: Approved, Not Qualified</h2>
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
            {_deal_reg_rows(approved_rows)}
          </tbody>
        </table>
      </div>
    </section>

    <section class="section">
      <h2>Stalled Channel Deals</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Deal Name</th>
              <th>Create Date</th>
              <th>Days in Stage</th>
              <th>Stage</th>
              <th>Owner</th>
              <th>Channel Deal Type</th>
              <th>Channel Partner</th>
              <th>Partner Contact Email</th>
            </tr>
          </thead>
          <tbody>
            {_stalled_rows(stalled)}
          </tbody>
        </table>
      </div>
    </section>

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
  </div>
</body>
</html>
"""
