# Channel Ops Weekly Report

## What this is / Goals

Every Monday, Isaac needs a Channel Ops snapshot: which deal regs are approved but not yet qualified, which channel deals have been sitting too long in an early stage, and two hygiene reminders (resellers list and meetings list). This script pulls that from HubSpot and turns it into a readable HTML file you can post in Slack, so you don't have to assemble it by hand.

## Current state / What it does

When you run it, the script talks to HubSpot, builds the report, and saves a file named `channelops_report_YYYY-MM-DD.html` (today's date) in the `output` folder. Open that file in a browser, look it over, then drag it into the Slack channel yourself. Posting is not automatic yet.

## How to run it

In PowerShell, from this folder:

```
.\venv\Scripts\Activate.ps1
python weekly_report.py
```

Then open the new file in the `output` folder (`channelops_report_YYYY-MM-DD.html`), review it, and drag it into Slack.

## Next steps / Known limitations

Slack posting is still manual. The next planned step is an automatic post using a Slack webhook — that function already exists in the code (`post_to_slack`) but is not used yet.

The two hygiene items (Resellers and Meetings) are static HubSpot links, not live tables. HubSpot does not offer an API for saved CRM views, so those stay as "please go check this list" reminders. The deal-reg and stalled-deals tables are live data, because those come from a full HubSpot data pull.
