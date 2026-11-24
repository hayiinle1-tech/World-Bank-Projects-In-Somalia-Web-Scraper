"""World Bank: projects + procurement notices (search.worldbank.org/api/v2). Free, no key."""
from __future__ import annotations

import time

from common import clean, get_json, iso_date, log, num

API = "https://search.worldbank.org/api/v2"
PAGE = 500
NOTICE_FIELDS = ("id,notice_type,noticedate,notice_status,submission_date,submission_deadline_date,"
                 "submission_deadline_time,project_id,project_name,bid_reference_no,bid_description,"
                 "procurement_group,procurement_method_name,contact_organization,contact_address,"
                 "contact_name,contact_email,contact_phone_no")


def _paginate(endpoint: str, params: dict, key: str) -> list[dict]:
    out, offset = [], 0
    while True:
        page = get_json(f"{API}/{endpoint}", {**params, "format": "json", "rows": PAGE, "os": offset})
        total = int(page.get("total") or 0)
        batch = page.get(key) or {}
        items = list(batch.values()) if isinstance(batch, dict) else list(batch)
        out.extend(items)
        offset += PAGE
        if not items or offset >= total:
            return out
        time.sleep(0.4)


def _sectors(p: dict) -> list[str]:
    names = [clean(p[f"sector{i}"].get("Name")) for i in range(1, 6)
             if isinstance(p.get(f"sector{i}"), dict) and p[f"sector{i}"].get("Name")]
    return list(dict.fromkeys(n for n in names if n))


def fetch(cfg: dict) -> dict:
    cc = cfg.get("country_code", "SO")
    result = {"projects": [], "notices": [], "news": []}

    for p in _paginate("projects", {"countrycode_exact": cc}, "projects"):
        pid = p.get("id")
        if not pid:
            continue
        result["projects"].append({
            "source": "World Bank",
            "source_id": pid,
            "ids": [pid],
            "title": clean(p.get("project_name")),
            "description": "",
            "status": clean(p.get("projectstatusdisplay") or p.get("status")),
            "funders": ["World Bank"],
            "implementers": [clean(p.get("impagency"))] if p.get("impagency") else [],
            "start": iso_date(p.get("boardapprovaldate")),
            "end": iso_date(p.get("closingdate")),
            "commitment_usd": num(p.get("curr_total_commitment")) or num(p.get("totalcommamt")) or num(p.get("totalamt")),
            "sectors": _sectors(p),
            "url": p.get("url") or f"https://projects.worldbank.org/en/projects-operations/project-detail/{pid}",
        })
    log(f"  World Bank projects: {len(result['projects'])}")

    if cfg.get("notices", True):
        for n in _paginate("procnotices", {"project_ctry_code": cc, "fl": NOTICE_FIELDS}, "procnotices"):
            nid = n.get("id")
            if not nid:
                continue
            result["notices"].append({
                "source": "World Bank",
                "source_id": nid,
                "title": clean(n.get("bid_description")) or clean(n.get("project_name")),
                "type": clean(n.get("notice_type")),
                "published": iso_date(n.get("noticedate") or n.get("submission_date")),
                "deadline": iso_date(n.get("submission_deadline_date")),
                "deadline_time": clean(n.get("submission_deadline_time")),
                "organization": clean(n.get("contact_organization")),
                "funder": "World Bank",
                "reference": clean(n.get("bid_reference_no")),
                "project_ids": [clean(n.get("project_id"))] if n.get("project_id") else [],
                "project_name": clean(n.get("project_name")),
                "method": clean(n.get("procurement_method_name")),
                "contact": {k: clean(n.get(f)) for k, f in (("name", "contact_name"), ("email", "contact_email"),
                                                           ("phone", "contact_phone_no"), ("address", "contact_address"))},
                "url": f"https://projects.worldbank.org/en/projects-operations/procurement-detail/{nid}",
            })
        log(f"  World Bank notices: {len(result['notices'])}")
    return result
