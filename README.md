# Channel Ops Weekly Report

## What this is / Goals

Every Monday, Isaac needs a Channel Ops snapshot: which deal regs are approved but not yet qualified, which channel deals have been sitting too long in an early stage, and two hygiene reminders (resellers list and meetings list). This script pulls that from HubSpot and turns it into a readable HTML file you can post in Slack, so you don't have to assemble it by hand.

## Current state / What it does

When you run `python scripts/weekly_report.py` from the project root, it talks to HubSpot, builds the report, and saves a file named `channelops_report_YYYY-MM-DD.html` (today's date) in the `output` folder. Open that file in a browser, look it over, then drag it into the Slack channel yourself. Posting is not automatic yet.

Python files live in `scripts/`. Each one has one job:

| File | Responsibility |
|---|---|
| `scripts/weekly_report.py` | Entry point: run the report, write the HTML file (`post_to_slack` lives here, unused for now) |
| `scripts/report_config.py` | Portal IDs, stage IDs, thresholds, HubSpot token, static hygiene links |
| `scripts/hubspot_client.py` | Talk to HubSpot (deal search + owner name lookup) |
| `scripts/report_data.py` | What counts as a deal-reg vs a stalled deal, and the overlap/dedup rule |
| `scripts/report_html.py` | Turn those rows into the HTML file you post |

## HubSpot pull: business logic

The weekly report makes two HubSpot deal searches. They are not the same population. **Deal regs** is a Channel registration-status view. **Stalled channel deals** is an early-stage, partner-known aging view. The CRO all-deals report should treat the stalled query as the starting point — and should not assume it already covers every stalled deal or every rep's book.

Portal: `47829307`. Deal record links: `https://app.hubspot.com/contacts/47829307/record/0-3/{deal_id}`.

### What "stalled" means (the query)

A deal is stalled when **all** of the following are true. Thresholds and filters are applied in `get_stalled_channel_deals()` in `scripts/report_data.py`.

1. **Stage is one of three early Realm Prospects stages** (`dealstage` IN):
   - `1391128198` → "0% - Deal Reg"
   - `appointmentscheduled` → "10% Discovery"
   - `qualifiedtobuy` → "20% Qualification"
2. **A channel partner is known:** `partner_company` has a value (`HAS_PROPERTY`).
3. **It is not an explicit direct deal:** `partner_company` is not `"No Partner - Direct"` (`EXCLUDED_PARTNER_VALUES` in `scripts/report_config.py`).
4. **Days in the current stage is greater than 14** (`STALLED_THRESHOLD_DAYS = 14` in `scripts/report_config.py`). Days are whole days from `hs_v2_date_entered_current_stage` to now (UTC). The comparison is `>` 14, not `>=` 14, so a deal at exactly 14 days is not stalled.


### HubSpot fields pulled, and why

**Stalled search** (CRM deal search `POST /crm/v3/objects/deals/search`, then owner lookup):

| Property | Why |
|---|---|
| `dealname` | Display name; hyperlinked to the HubSpot deal record |
| `createdate` | "Create Date" column (first 10 chars, formatted `Mon DD, YYYY`) |
| `dealstage` | Filter + mapped to a friendly stage label |
| `hs_v2_date_entered_current_stage` | Sole input for days-in-stage |
| `hubspot_owner_id` | Resolved to a display name via `/crm/v3/owners/{id}` (cached). Missing owner → "Unassigned" |
| `partner_deal_classification` | "Channel Deal Type" column (Partner Sourced / Partner Influenced / etc.) |
| `partner_company` | Channel-partner filter **and** "Channel Partner" column |
| `partner_contact_email` | "Partner Contact Email" column |


**Deal-reg search** (separate; Channel-only):

| Property | Why |
|---|---|
| `deal_reg_status` | Filter: `Approved` for the table; a second search of `Qualified` for the headline counts only |
| `dealname` | Display + record link |
| `deal_reg_approval_date` | Days since approval |
| `hubspot_owner_id` | Owner column |
| `partner_company`, `partner_contact_email` | Partner columns |

### Dedup, dates, and stage mapping

- **API pagination:** deal search pages at 200; no server-side sort. Client sorts stalled rows by `days_in_stage` descending.
- **Deal-reg vs stalled overlap:** `exclude_approved_deal_regs()` in `scripts/report_data.py` removes any stalled deal whose id is already in the "Approved, Not Qualified" table so the two tables do not list the same record twice. A deal can still match both queries before that step (Approved deal-reg sitting in Deal Reg / Discovery / Qualification for >14 days).
- **Days math:** `days_since()` in `scripts/report_data.py` accepts `YYYY-MM-DD` or an ISO datetime. Unparseable values become `None`. If `hs_v2_date_entered_current_stage` is missing or unparseable, that deal is omitted from the stalled table (it is not shown as unknown).
- **Stage labels:** hardcoded map of those three IDs in `scripts/report_config.py`. Any other stage id would print as the raw HubSpot id.
- **Display coloring is not the stalled definition.** The query cutoff is >14 days. Row/badge colors are a separate presentation layer in `scripts/report_html.py` (`URGENCY_WATCH` / `URGENCY_WARN` / `URGENCY_CRITICAL`: watch 14–29d, warn 30–89d, critical 90d+). The on-page legend is generated from those same constants. That coloring is Channel-report UI, not HubSpot filter logic, and should not be copied into a CRO report until thresholds are decided from all-deals data.


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

The two hygiene items (Resellers and Meetings) are static HubSpot links, not live tables. HubSpot does not offer an API for saved CRM views, so those stay as "please go check this list" reminders. The deal-reg and stalled-deals tables are live data, because those come from a full HubSpot data pull.

If HubSpot is unreachable or returns an error, the script exits with `ERROR: HubSpot request failed: ...` and does not write a report file.
