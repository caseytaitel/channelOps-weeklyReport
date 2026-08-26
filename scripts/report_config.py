"""Shared configuration for the weekly Channel Ops report.

ASSUMPTIONS (flagged, not silently baked in - change here if wrong):
  - "Channel partner is known" excludes partner_company == "No Partner - Direct".
    Add/remove values in EXCLUDED_PARTNER_VALUES below.
  - Record links use Deal Name (clickable to the record) rather than bare Record ID.
  - Closed deals are out of scope (hs_is_closed = false). Stage itself does not
    otherwise limit which open Channel deals can appear as stalled.
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv(".env.local")

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

# Used if the pipelines endpoint is unavailable. Live labels are loaded from HubSpot.
FALLBACK_STAGE_LABELS = {
    "1391128198": "0% - Deal Reg",
    "appointmentscheduled": "10% Discovery",
    "qualifiedtobuy": "20% Qualification",
    "presentationscheduled": "30% Planning",
    "decisionmakerboughtin": "50% Evaluation",
    "1047781720": "Closed Won - 100%",
    "1047781721": "Closed Lost - 0%",
    "1225089961": "Closed No Opportunity - 0%",
}

# Unqualified deal regs (Approved, not Qualified) surface after this many days
# since deal_reg_approval_date. Comparison is `>` not `>=`.
DEAL_REG_SURFACE_DAYS = 14

# All other open Channel deals surface as stalled after this many days in the
# current deal stage. Comparison is `>` not `>=`.
STALLED_THRESHOLD_DAYS = 30

# Fiscal year for Stalled close-date grouping. Q1 Feb–Apr, Q2 May–Jul,
# Q3 Aug–Oct, Q4 Nov–Jan.
FY_START_MONTH = 2

# See ASSUMPTIONS above
EXCLUDED_PARTNER_VALUES = ["No Partner - Direct"]

# Static links (no API access exists for saved "views" - confirmed against both the
# HubSpot connector and the public REST API docs)
RESELLERS_VIEW_URL = f"https://app.hubspot.com/contacts/{PORTAL_ID}/objects/0-2/views/67142806/list"
MEETINGS_VIEW_URL = f"https://app.hubspot.com/contacts/{PORTAL_ID}/objects/0-47/views/68020096/list"

DEAL_RECORD_URL = f"https://app.hubspot.com/contacts/{PORTAL_ID}/record/0-3/{{deal_id}}"

OUTPUT_DIR = "output"
