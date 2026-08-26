#!/usr/bin/env python3
"""
Weekly RevOps report for Isaac.

Pulls all open Channel deals from HubSpot (partner known, not Direct), then
presents two action lists:
  1. Unqualified Deal Regs — Approved, not Qualified, >14 days since approval
  2. Stalled deals — every other open Channel deal, >30 days in current stage
     (any open stage)
Plus static links for Resellers hygiene and Meeting hygiene (no API pull
possible for saved HubSpot views).

USAGE
  1. Set env vars (via .env.local in the project root):
       HUBSPOT_TOKEN        - HubSpot private app access token (scopes: crm.objects.deals.read,
                               crm.objects.owners.read)
  2. From the project root: python scripts/weekly_report.py
  3. Open output/channelops_report_YYYY-MM-DD.html, review, then drag into Slack.
"""

import os
import sys
from datetime import datetime

import requests

from report_config import OUTPUT_DIR, SLACK_WEBHOOK_URL
from report_data import get_channel_report
from report_html import build_html_report


# Kept for a future automated-posting version; not called from main().
def post_to_slack(message):
    resp = requests.post(SLACK_WEBHOOK_URL, json={"text": message}, timeout=30)
    resp.raise_for_status()


def main():
    now = datetime.now()
    try:
        report_data = get_channel_report(now)
    except requests.RequestException as e:
        sys.exit(f"ERROR: HubSpot request failed: {e}")

    report = build_html_report(report_data, now)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filename = f"channelops_report_{now.strftime('%Y-%m-%d')}.html"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Wrote {filepath}. Open and review it before manually posting to Slack.")


if __name__ == "__main__":
    main()
