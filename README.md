# Channel Ops Weekly Report

## What this is / Goals

Every Monday, Isaac needs a Channel Ops snapshot: which Approved deal regs have not been Qualified yet and are aging, which other open Channel deals have been sitting too long in their current stage, and two hygiene reminders (resellers list and meetings list). This script pulls that from HubSpot and turns it into a tabbed HTML file you can post in Slack, so you don't have to assemble it by hand.

## Current state / What it does

When you run `python scripts/weekly_report.py` from the project root, it talks to HubSpot, builds the report, and saves a file named `channelops_report_YYYY-MM-DD.html` (today's date) in the `output` folder. Open that file in a browser, look it over, then drag it into the Slack channel yourself. Posting is not automatic yet.

The HTML has three tabs: **Overview**, **Unqualified Deal Regs**, **Stalled Deals**. Open it in a browser so the tabs work; Slack's file preview may not.

**Overview** is a number summary: open Channel deals, deal regs with a known status, Qualified, then the two review counts (unqualified deal regs and stalled deals). The other two tabs are the action lists.

Python files live in `scripts/`. Each one has one job:

| File | Responsibility |
|---|---|
| `scripts/weekly_report.py` | Entry point: run the report, write the HTML file (`post_to_slack` lives here, unused for now) |
| `scripts/report_config.py` | Portal IDs, thresholds, HubSpot token, static hygiene links |
| `scripts/hubspot_client.py` | Talk to HubSpot (deal search, owner names, stage labels) |
| `scripts/report_data.py` | One Channel pull; split into Unqualified Deal Regs vs Stalled |
| `scripts/report_html.py` | Turn those rows into the tabbed HTML file you post |

## HubSpot pull: business logic

There is **one population**: open Channel deals. Presentation splits that population into two action lists so a deal appears on at most one tab.

Portal: `47829307`. Deal record links: `https://app.hubspot.com/contacts/47829307/record/0-3/{deal_id}`.

### Shared Channel filter

Applied in `get_channel_report()` in `scripts/report_data.py`:

1. **A channel partner is known:** `partner_company` has a value (`HAS_PROPERTY`).
2. **It is not an explicit direct deal:** `partner_company` is not `"No Partner - Direct"` (`EXCLUDED_PARTNER_VALUES` in `scripts/report_config.py`).
3. **The deal is still open:** `hs_is_closed` is `false`. Closed Won / Closed Lost / Closed No Opportunity are out of scope. **Open stage otherwise does not matter** — 0% through 50%+ can all appear as stalled.

### Unqualified Deal Regs tab

A deal is on this tab when **all** of the following are true:

1. It passed the shared Channel filter.
2. `deal_reg_status` is `Approved` (not yet `Qualified`).
3. Days since `deal_reg_approval_date` is **greater than 14** (`DEAL_REG_SURFACE_DAYS`). A missing approval date is still shown, so it is not dropped silently.

### Stalled Deals tab

A deal is on this tab when **all** of the following are true:

1. It passed the shared Channel filter.
2. It is **not** on the Unqualified Deal Regs tab (no deal reg, or already Qualified, or Approved but not yet past 14 days since approval).
3. Days in the current stage is **greater than 30** (`STALLED_THRESHOLD_DAYS`). Days are whole days from `hs_v2_date_entered_current_stage` to now (UTC). A deal at exactly 30 days is not stalled. Missing stage-entry dates are omitted (not shown as unknown).

The table is then **grouped by HubSpot close date** for display. That does not change who is stalled. Fiscal year starts Feb 1 (Q1 Feb–Apr, Q2 May–Jul, Q3 Aug–Oct, Q4 Nov–Jan). Empty groups are omitted. Order: **Past close date**, remaining quarters of the current fiscal year, next FY, then **No close date**. Inside each group, longest in stage first.

### HubSpot fields pulled, and why

One CRM deal search (`POST /crm/v3/objects/deals/search`), then owner lookup and a pipelines call for stage labels:

| Property | Why |
|---|---|
| `partner_company` | Channel filter **and** "Channel Partner" column |
| `hs_is_closed` | Open-deals filter |
| `deal_reg_status` | Overview totals (known status vs Qualified) and Unqualified Deal Regs filter |
| `deal_reg_approval_date` | Days since approval (Unqualified Deal Regs) |
| `dealname` | Display name; hyperlinked to the HubSpot deal record |
| `closedate` | Stalled "Close Date" column and fiscal-quarter grouping |
| `dealstage` | Stalled "Stage" column (label from `/crm/v3/pipelines/deals`) |
| `hs_v2_date_entered_current_stage` | Days-in-stage for Stalled |
| `hubspot_owner_id` | Resolved to a display name via `/crm/v3/owners/{id}` (cached). Missing owner → "Unassigned" |
| `partner_deal_classification` | Stalled "Channel Deal Type" column |
| `partner_contact_email` | "Partner Contact Email" column |

### Dedup, dates, and coloring

- **API pagination:** deal search pages at 200; no server-side sort. Client sorts Unqualified Deal Regs by days since approval descending, Stalled by `days_in_stage` descending, then groups Stalled by close date.
- **One deal, one tab:** Unqualified Deal Regs is decided first. Those ids are not also listed as Stalled.
- **Days math:** `days_since()` in `scripts/report_data.py` accepts `YYYY-MM-DD` or an ISO datetime. Unparseable values become `None`.
- **Display coloring is not the query definition.** Cutoffs are >14 days (deal regs) and >30 days (stalled). Row/badge colors in `scripts/report_html.py` are separate: under 30 uncolored, yellow 30–59d, orange 60–89d, red 90d+. The Unqualified Deal Regs and Stalled Deals tabs show those bands on the right of the tab bar.

## How to run it

Always run from this project folder (the one that contains `scripts/`, `output/`, and `.env.local`), not from inside `scripts/`. The token file and the HTML output path are relative to that folder.

You need a `.env.local` file here with `HUBSPOT_TOKEN` set (HubSpot private app token; scopes `crm.objects.deals.read` and `crm.objects.owners.read`).

In PowerShell, from this folder:

```
.\venv\Scripts\Activate.ps1
python scripts\weekly_report.py
```

Then open the new file in the `output` folder (`channelops_report_YYYY-MM-DD.html`), review it, and drag it into Slack.

A local Windows Task Scheduler job runs `run_weekly_report.bat` (Mondays at 7am on this machine). That bat file is gitignored because it is machine-specific. It `cd`s to this folder, activates `venv`, then runs `python scripts\weekly_report.py`.

`requirements.txt` is **not something you use on a normal Monday.** Your `venv` already has the two Python packages this script needs (`requests` and `python-dotenv`). That file is a shopping list for a **new** environment only: a coworker cloning the repo, or you on a new laptop. Then: create a venv, `pip install -r requirements.txt`, add `.env.local`. Git does not include `venv/` or `.env.local`, so a clone is code-only until those two steps.

## Next steps / Known limitations

Slack posting is still manual. The next planned step is an automatic post using a Slack webhook — that function already exists in `scripts/weekly_report.py` (`post_to_slack`) but is not used yet.

The two hygiene items (Resellers and Meetings) are static HubSpot links, not live tables. HubSpot does not offer an API for saved CRM views, so those stay as "please go check this list" reminders.

If HubSpot is unreachable or returns an error, the script exits with `ERROR: HubSpot request failed: ...` and does not write a report file.
