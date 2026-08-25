"""HubSpot CRM HTTP helpers used by the weekly report."""

import requests

from report_config import HEADERS, HUBSPOT_API

_owner_cache = {}


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
    """Resolve a hubspot_owner_id to a display name, with caching.

    Archived owners 404 on the default endpoint. Retry with archived=true so
    deactivated reps still show a real name (e.g. Leo Clougherty) instead of
    "Owner {id}".
    """
    if not owner_id:
        return "Unassigned"
    if owner_id in _owner_cache:
        return _owner_cache[owner_id]

    def _display_name(data):
        return (
            f"{data.get('firstName', '')} {data.get('lastName', '')}".strip()
            or data.get("email")
            or f"Owner {owner_id}"
        )

    resp = requests.get(
        f"{HUBSPOT_API}/crm/v3/owners/{owner_id}",
        headers=HEADERS,
        timeout=30,
    )
    if resp.status_code == 200:
        _owner_cache[owner_id] = _display_name(resp.json())
        return _owner_cache[owner_id]

    archived = requests.get(
        f"{HUBSPOT_API}/crm/v3/owners/{owner_id}",
        headers=HEADERS,
        params={"archived": "true"},
        timeout=30,
    )
    if archived.status_code == 200:
        _owner_cache[owner_id] = _display_name(archived.json())
        return _owner_cache[owner_id]

    _owner_cache[owner_id] = f"Owner {owner_id}"
    return _owner_cache[owner_id]
