#!/usr/bin/env python3
"""
Weekly RevOps report for Isaac.

Pulls from HubSpot:
  1. Deal Regs: Approved vs Qualified counts + table of Approved-not-yet-Qualified deals
  2. Stalled channel deals (Deal Reg / Discovery / Qualification, partner known, >14 days in stage)
  3. Static links + reminders for Resellers hygiene and Meeting hygiene (no API pull possible
     for these two - see chat history: HubSpot has no API for saved "views", only for Lists,
     and these are views, not lists)

USAGE
  1. pip install requests python-dotenv
  2. Set env vars (via .env.local):
       HUBSPOT_TOKEN        - HubSpot private app access token (scopes: crm.objects.deals.read,
                               crm.objects.owners.read)
  3. Run: python weekly_report.py
  4. Open output/channelops_report_YYYY-MM-DD.html, review, then drag into Slack.

ASSUMPTIONS (flagged, not silently baked in - change here if wrong):
  - "Channel partner is known" excludes partner_company == "No Partner - Direct".
    Add/remove values in EXCLUDED_PARTNER_VALUES below.
  - Record links use Deal Name (clickable to the record) rather than bare Record ID.
"""

import html
import os
import sys
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv(".env.local")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

HUBSPOT_TOKEN = os.environ.get("HUBSPOT_TOKEN")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

if not HUBSPOT_TOKEN:
    sys.exit("ERROR: HUBSPOT_TOKEN environment variable not set.")

PORTAL_ID = "47829307"
HUBSPOT_API = "https://api.hubapi.com"
HEADERS = {
    "Authorization": f"Bearer {HUBSPOT_TOKEN}",
    "Content-Type": "application/json",
}

# Stage IDs for the "Realm Prospects" pipeline, confirmed against live portal data
STALLED_STAGE_IDS = ["1391128198", "appointmentscheduled", "qualifiedtobuy"]
STAGE_LABELS = {
    "1391128198": "0% - Deal Reg",
    "appointmentscheduled": "10% Discovery",
    "qualifiedtobuy": "20% Qualification",
}
STALLED_THRESHOLD_DAYS = 14

# See ASSUMPTIONS above
EXCLUDED_PARTNER_VALUES = ["No Partner - Direct"]

# Static links (no API access exists for saved "views" - confirmed against both the
# HubSpot connector and the public REST API docs)
RESELLERS_VIEW_URL = f"https://app.hubspot.com/contacts/{PORTAL_ID}/objects/0-2/views/67142806/list"
MEETINGS_VIEW_URL = f"https://app.hubspot.com/contacts/{PORTAL_ID}/objects/0-47/views/68020096/list"

DEAL_RECORD_URL = f"https://app.hubspot.com/contacts/{PORTAL_ID}/record/0-3/{{deal_id}}"

OUTPUT_DIR = "output"

_owner_cache = {}


# ---------------------------------------------------------------------------
# HubSpot API helpers
# ---------------------------------------------------------------------------

def hubspot_search_deals(filter_groups, properties, limit=200):
    """Search deals with pagination. Returns a list of result dicts."""
    results = []
    after = None
    while True:
        body = {
            "filterGroups": filter_groups,
            "properties": properties,
            "limit": limit,
        }
        if after:
            body["after"] = after
        resp = requests.post(
            f"{HUBSPOT_API}/crm/v3/objects/deals/search",
            headers=HEADERS,
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        results.extend(data.get("results", []))
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    return results


def get_owner_name(owner_id):
    """Resolve a hubspot_owner_id to a display name, with caching."""
    if not owner_id:
        return "Unassigned"
    if owner_id in _owner_cache:
        return _owner_cache[owner_id]
    resp = requests.get(
        f"{HUBSPOT_API}/crm/v3/owners/{owner_id}",
        headers=HEADERS,
        timeout=30,
    )
    if resp.status_code != 200:
        _owner_cache[owner_id] = f"Owner {owner_id}"
        return _owner_cache[owner_id]
    data = resp.json()
    name = f"{data.get('firstName', '')} {data.get('lastName', '')}".strip() or data.get("email", owner_id)
    _owner_cache[owner_id] = name
    return name


def days_since(date_str):
    """date_str is 'YYYY-MM-DD' or an ISO datetime string. Returns whole days elapsed."""
    if not date_str:
        return None
    try:
        if "T" in date_str:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).days
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Report 1: Deal Regs vs Intro Demos (Approved vs Qualified) + approved-not-qualified table
# ---------------------------------------------------------------------------

def get_deal_reg_report():
    approved = hubspot_search_deals(
        filter_groups=[{"filters": [{"propertyName": "deal_reg_status", "operator": "EQ", "value": "Approved"}]}],
        properties=["dealname", "deal_reg_approval_date", "hubspot_owner_id", "partner_company", "partner_contact_email"],
    )
    qualified = hubspot_search_deals(
        filter_groups=[{"filters": [{"propertyName": "deal_reg_status", "operator": "EQ", "value": "Qualified"}]}],
        properties=["dealname"],
    )

    rows = []
    for deal in approved:
        p = deal["properties"]
        rows.append({
            "id": deal["id"],
            "name": p.get("dealname", "(unnamed)"),
            "days_since_approval": days_since(p.get("deal_reg_approval_date")),
            "owner": get_owner_name(p.get("hubspot_owner_id")),
            "partner": p.get("partner_company") or "-",
            "partner_email": p.get("partner_contact_email") or "-",
        })
    rows.sort(key=lambda r: (r["days_since_approval"] is None, r["days_since_approval"]), reverse=True)

    return {
        "approved_count": len(approved),
        "qualified_count": len(qualified),
        "approved_not_qualified": rows,
    }


# ---------------------------------------------------------------------------
# Report 2: Stalled channel deals
# ---------------------------------------------------------------------------

def get_stalled_channel_deals():
    all_candidates = hubspot_search_deals(
        filter_groups=[{
            "filters": [
                {"propertyName": "dealstage", "operator": "IN", "values": STALLED_STAGE_IDS},
                {"propertyName": "partner_company", "operator": "HAS_PROPERTY"},
            ]
        }],
        properties=[
            "dealname", "createdate", "dealstage", "hs_v2_date_entered_current_stage",
            "hubspot_owner_id", "partner_deal_classification", "partner_company", "partner_contact_email",
        ],
    )

    rows = []
    for deal in all_candidates:
        p = deal["properties"]
        partner = p.get("partner_company")
        if partner in EXCLUDED_PARTNER_VALUES:
            continue
        stage_days = days_since(p.get("hs_v2_date_entered_current_stage"))
        if stage_days is None or stage_days <= STALLED_THRESHOLD_DAYS:
            continue
        rows.append({
            "id": deal["id"],
            "name": p.get("dealname", "(unnamed)"),
            "create_date": (p.get("createdate") or "")[:10],
            "days_in_stage": stage_days,
            "stage_label": STAGE_LABELS.get(p.get("dealstage"), p.get("dealstage")),
            "owner": get_owner_name(p.get("hubspot_owner_id")),
            "channel_deal_type": p.get("partner_deal_classification") or "-",
            "partner": partner,
            "partner_email": p.get("partner_contact_email") or "-",
        })

    rows.sort(key=lambda r: r["days_in_stage"], reverse=True)
    return rows


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

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


def _deal_reg_rows(rows):
    if not rows:
        return _empty_row(5, "None currently — all Approved deals are already Qualified.")
    parts = []
    for r in rows:
        days = r["days_since_approval"]
        parts.append(
            "<tr class=\"{cls}\">"
            "<td>{name}</td>"
            "<td class=\"num\">{badge}</td>"
            "<td>{owner}</td>"
            "<td>{partner}</td>"
            "<td>{email}</td>"
            "</tr>".format(
                cls=_urgency_class(days),
                name=_deal_name_cell(r["id"], r["name"]),
                badge=_days_badge(days),
                owner=_esc(r["owner"]),
                partner=_esc(r["partner"]),
                email=_esc(r["partner_email"]),
            )
        )
    return "\n".join(parts)


def _stalled_rows(rows):
    if not rows:
        return _empty_row(8, "None currently.")
    parts = []
    for r in rows:
        days = r["days_in_stage"]
        parts.append(
            "<tr class=\"{cls}\">"
            "<td>{name}</td>"
            "<td class=\"nowrap\">{created}</td>"
            "<td class=\"num\">{badge}</td>"
            "<td>{stage}</td>"
            "<td>{owner}</td>"
            "<td>{dtype}</td>"
            "<td>{partner}</td>"
            "<td>{email}</td>"
            "</tr>".format(
                cls=_urgency_class(days),
                name=_deal_name_cell(r["id"], r["name"]),
                created=_esc(_format_date(r["create_date"])),
                badge=_days_badge(days),
                stage=_esc(r["stage_label"]),
                owner=_esc(r["owner"]),
                dtype=_esc(r["channel_deal_type"]),
                partner=_esc(r["partner"]),
                email=_esc(r["partner_email"]),
            )
        )
    return "\n".join(parts)


def build_html_report(deal_reg, stalled, now):
    """Return a complete, self-contained HTML document for the weekly RevOps report."""
    today = now.strftime("%B %d, %Y")
    approved_count = deal_reg["approved_count"]
    qualified_count = deal_reg["qualified_count"]
    deal_reg_total = approved_count + qualified_count
    stalled_count = len(stalled)
    approved_rows = deal_reg["approved_not_qualified"]

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
    --header: #152033;
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
        <span><i class="dot dot-watch"></i> 14–29d</span>
        <span><i class="dot dot-warn"></i> 30–89d</span>
        <span><i class="dot dot-crit"></i> 90d+</span>
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


# Kept for a future automated-posting version; not called from main().
def post_to_slack(message):
    resp = requests.post(SLACK_WEBHOOK_URL, json={"text": message}, timeout=30)
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def exclude_approved_deal_regs(stalled, deal_reg):
    """Drop stalled deals already listed in Approved, Not Qualified so the two tables don't overlap."""
    approved_ids = {r["id"] for r in deal_reg["approved_not_qualified"]}
    return [r for r in stalled if r["id"] not in approved_ids]


def main():
    now = datetime.now()
    deal_reg = get_deal_reg_report()
    stalled = exclude_approved_deal_regs(get_stalled_channel_deals(), deal_reg)
    report = build_html_report(deal_reg, stalled, now)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filename = f"channelops_report_{now.strftime('%Y-%m-%d')}.html"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Wrote {filepath}. Open and review it before manually posting to Slack.")


if __name__ == "__main__":
    main()