"""HubSpot queries and row shaping for the weekly Channel Ops report."""

from datetime import datetime, timezone

from hubspot_client import get_owner_name, get_stage_labels, hubspot_search_deals
from report_config import (
    DEAL_REG_SURFACE_DAYS,
    EXCLUDED_PARTNER_VALUES,
    FY_START_MONTH,
    STALLED_THRESHOLD_DAYS,
)

CHANNEL_DEAL_PROPERTIES = [
    "dealname",
    "closedate",
    "dealstage",
    "hs_v2_date_entered_current_stage",
    "hubspot_owner_id",
    "partner_deal_classification",
    "partner_company",
    "partner_contact_email",
    "deal_reg_status",
    "deal_reg_approval_date",
]


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


def _is_unqualified_deal_reg(status, days_since_approval):
    """Approved deal regs Isaac should see: past the approval-age cutoff.

    Missing approval dates are surfaced so they are not silently dropped.
    """
    if status != "Approved":
        return False
    if days_since_approval is None:
        return True
    return days_since_approval > DEAL_REG_SURFACE_DAYS


def _parse_close_date(date_str):
    """Return a date from 'YYYY-MM-DD', or None if missing/invalid."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _fiscal_year(d):
    """Calendar year the FY ending on this date ends in. Feb 1, 2026 → 2027."""
    if d.month >= FY_START_MONTH:
        return d.year + 1
    return d.year


def _fiscal_quarter(d):
    """1–4 for a Feb-start fiscal year. Aug → 3, Jan → 4."""
    offset = (d.month - FY_START_MONTH) % 12
    return offset // 3 + 1


def _fy_label(year):
    return f"FY{year % 100:02d}"


def _close_period_sections(deals, as_of):
    """Split deals into past / remaining FY quarters / next FY / no date.

    Empty sections are omitted. Order inside each section is preserved
    (callers pass deals already sorted by days in stage).
    """
    if isinstance(as_of, datetime):
        as_of = as_of.date()
    as_of_fy = _fiscal_year(as_of)
    as_of_q = _fiscal_quarter(as_of)
    later_label = _fy_label(as_of_fy + 1)
    buckets = [("Past close date", [])]
    for q in range(as_of_q, 5):
        buckets.append((f"Q{q}", []))
    buckets.append((later_label, []))
    buckets.append(("No close date", []))
    by_label = {label: rows for label, rows in buckets}

    for deal in deals:
        close = _parse_close_date(deal.get("close_date"))
        if close is None:
            by_label["No close date"].append(deal)
        elif close < as_of:
            by_label["Past close date"].append(deal)
        elif _fiscal_year(close) == as_of_fy and _fiscal_quarter(close) >= as_of_q:
            by_label[f"Q{_fiscal_quarter(close)}"].append(deal)
        else:
            by_label[later_label].append(deal)

    return [(label, rows) for label, rows in buckets if rows]


def get_channel_report(now=None):
    """One Channel pull, then split into Unqualified Deal Regs vs Stalled.

    Population: partner known, not Direct, still open (hs_is_closed = false).
    A deal appears on at most one tab. Stalled rows are grouped by fiscal
    close date for display; that grouping does not change who is stalled.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    stage_labels = get_stage_labels()
    deals = hubspot_search_deals(
        filter_groups=[{
            "filters": [
                {"propertyName": "partner_company", "operator": "HAS_PROPERTY"},
                {"propertyName": "hs_is_closed", "operator": "EQ", "value": "false"},
            ]
        }],
        properties=CHANNEL_DEAL_PROPERTIES,
    )

    unqualified_deal_regs = []
    stalled = []
    deal_reg_count = 0
    qualified_count = 0
    channel_count = 0

    for deal in deals:
        p = deal["properties"]
        partner = p.get("partner_company")
        if partner in EXCLUDED_PARTNER_VALUES:
            continue
        channel_count += 1

        status = p.get("deal_reg_status") or ""
        if status:
            deal_reg_count += 1
        if status == "Qualified":
            qualified_count += 1

        days_since_approval = days_since(p.get("deal_reg_approval_date"))

        if _is_unqualified_deal_reg(status, days_since_approval):
            identity, _ = _deal_identity(deal)
            unqualified_deal_regs.append({
                **identity,
                "days_since_approval": days_since_approval,
                "partner": partner,
            })
            continue

        stage_days = days_since(p.get("hs_v2_date_entered_current_stage"))
        if stage_days is None or stage_days <= STALLED_THRESHOLD_DAYS:
            continue
        identity, _ = _deal_identity(deal)
        stalled.append({
            **identity,
            "close_date": (p.get("closedate") or "")[:10],
            "days_in_stage": stage_days,
            "stage_label": stage_labels.get(p.get("dealstage"), p.get("dealstage")),
            "channel_deal_type": p.get("partner_deal_classification") or "-",
            "partner": partner,
        })

    unqualified_deal_regs.sort(
        key=lambda r: (r["days_since_approval"] is None, r["days_since_approval"]),
        reverse=True,
    )
    stalled.sort(key=lambda r: r["days_in_stage"], reverse=True)

    return {
        "channel_count": channel_count,
        "deal_reg_count": deal_reg_count,
        "qualified_count": qualified_count,
        "unqualified_deal_regs": unqualified_deal_regs,
        "stalled": stalled,
        "stalled_sections": _close_period_sections(stalled, now),
    }
