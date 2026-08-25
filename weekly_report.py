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
  1. pip install -r requirements.txt
  2. Set env vars (via .env.local):
       HUBSPOT_TOKEN        - HubSpot private app access token (scopes: crm.objects.deals.read,
                               crm.objects.owners.read)
  3. Run: python weekly_report.py
  4. Open output/channelops_report_YYYY-MM-DD.html, review, then drag into Slack.
"""

import os
import sys
from datetime import datetime

import requests

from report_config import OUTPUT_DIR, SLACK_WEBHOOK_URL
from report_data import (
    exclude_approved_deal_regs,
    get_deal_reg_report,
    get_stalled_channel_deals,
)
from report_html import build_html_report


# Kept for a future automated-posting version; not called from main().
def post_to_slack(message):
    resp = requests.post(SLACK_WEBHOOK_URL, json={"text": message}, timeout=30)
    resp.raise_for_status()


def main():
    now = datetime.now()
    try:
        deal_reg = get_deal_reg_report()
        stalled = exclude_approved_deal_regs(get_stalled_channel_deals(), deal_reg)
    except requests.RequestException as e:
        sys.exit(f"ERROR: HubSpot request failed: {e}")

    report = build_html_report(deal_reg, stalled, now)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filename = f"channelops_report_{now.strftime('%Y-%m-%d')}.html"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Wrote {filepath}. Open and review it before manually posting to Slack.")


if __name__ == "__main__":
    main()
