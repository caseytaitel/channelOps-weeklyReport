"""HubSpot queries and row shaping for the weekly Channel Ops report."""

from datetime import datetime, timezone

from hubspot_client import get_owner_name, hubspot_search_deals
from report_config import (
    EXCLUDED_PARTNER_VALUES,
    STAGE_LABELS,
    STALLED_STAGE_IDS,
    STALLED_THRESHOLD_DAYS,
)


def _deal_identity(deal):
    """Fields shared by both report tables: id, name, owner, partner email."""
    p = deal["properties"]
    return {
        "id": deal["id"],
        "name": p.get("dealname", "(unnamed)"),
        "owner": get_owner_name(p.get("hubspot_owner_id")),
        "partner_email": p.get("partner_contact_email") or "-",
    }, p


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
        identity, p = _deal_identity(deal)
        rows.append({
            **identity,
            "days_since_approval": days_since(p.get("deal_reg_approval_date")),
            "partner": p.get("partner_company") or "-",
        })
    rows.sort(key=lambda r: (r["days_since_approval"] is None, r["days_since_approval"]), reverse=True)

    return {
        "approved_count": len(approved),
        "qualified_count": len(qualified),
        "approved_not_qualified": rows,
    }


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
        identity, _ = _deal_identity(deal)
        rows.append({
            **identity,
            "create_date": (p.get("createdate") or "")[:10],
            "days_in_stage": stage_days,
            "stage_label": STAGE_LABELS.get(p.get("dealstage"), p.get("dealstage")),
            "channel_deal_type": p.get("partner_deal_classification") or "-",
            "partner": partner,
        })

    rows.sort(key=lambda r: r["days_in_stage"], reverse=True)
    return rows


def exclude_approved_deal_regs(stalled, deal_reg):
    """Drop stalled deals already listed in Approved, Not Qualified so the two tables don't overlap."""
    approved_ids = {r["id"] for r in deal_reg["approved_not_qualified"]}
    return [r for r in stalled if r["id"] not in approved_ids]
