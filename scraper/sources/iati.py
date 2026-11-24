"""IATI (International Aid Transparency Initiative) via the free D-Portal API.

IATI is where 1,000+ funders publish their aid projects: AfDB, UN agencies (UNDP, UNICEF,
WFP, FAO, IOM...), the EU, USAID, FCDO (UK), Germany, Sweden, Norway, Türkiye (TIKA),
the World Bank itself, and many NGOs. No key or approval needed.
"""
from __future__ import annotations

import time
import urllib.parse

from common import clean, extract_ids, get_json, iso_date, log

API = "https://d-portal.org/q.json"
PAGE = 1000
STATUS = {1: "Pipeline", 2: "Active", 3: "Finalisation", 4: "Closed", 5: "Cancelled", 6: "Suspended"}
FIELDS = "aid,reporting,reporting_ref,funder_ref,title,status_code,day_start,day_end,description,commitment,spend"


def fetch(cfg: dict) -> dict:
    cc = cfg.get("country_code", "SO")
    statuses = cfg.get("status_codes", "1|2")  # pipeline + implementation by default
    rows, offset = [], 0
    while True:
        page = get_json(API, {"from": "act,country", "country_code": cc, "status_code": statuses,
                              "select": FIELDS, "orderby": "aid", "limit": PAGE, "offset": offset}, timeout=120)
        batch = page.get("rows") or []
        rows.extend(batch)
        log(f"  IATI: {len(rows)}")
        if len(batch) < PAGE:
            break
        offset += PAGE
        time.sleep(0.5)

    projects = []
    for r in rows:
        aid = r.get("aid")
        if not aid:
            continue
        ids = {aid} | extract_ids(aid, r.get("title"), r.get("reporting_ref"), r.get("funder_ref"))
        for ref in (r.get("funder_ref"),):
            if ref and ref != r.get("reporting_ref"):
                ids.add(ref)  # links an implementer's record to its funder's record
        projects.append({
            "source": "IATI",
            "source_id": aid,
            "ids": sorted(ids),
            "title": clean(r.get("title")),
            "description": clean(r.get("description"), 500),
            "status": STATUS.get(r.get("status_code"), ""),
            "funders": [clean(r.get("reporting"))] if r.get("reporting") else [],
            "implementers": [],
            "start": iso_date(r.get("day_start")),
            "end": iso_date(r.get("day_end")),
            "commitment_usd": float(r.get("commitment") or 0) or float(r.get("spend") or 0),
            "sectors": [],
            "url": f"https://d-portal.org/ctrack.html#view=act&aid={urllib.parse.quote(aid, safe='')}",
        })
    return {"projects": projects, "notices": [], "news": []}
