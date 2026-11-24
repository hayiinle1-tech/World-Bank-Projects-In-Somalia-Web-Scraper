"""ReliefWeb (UN OCHA) consultancy opportunities in Somalia. OPTIONAL.

Since Nov 2025 ReliefWeb only answers requests carrying a pre-approved "appname".
Request one free at https://apidoc.reliefweb.int/ and save it as a GitHub secret named
RELIEFWEB_APPNAME. Without it this source is skipped automatically.
"""
from __future__ import annotations

import os

from common import clean, get_json, iso_date, log

API = "https://api.reliefweb.int/v2/jobs"


def fetch(cfg: dict) -> dict:
    appname = os.environ.get("RELIEFWEB_APPNAME", "").strip()
    if not appname:
        log("  ReliefWeb: skipped (no RELIEFWEB_APPNAME secret)")
        return {"projects": [], "notices": [], "news": []}
    params = [("appname", appname), ("filter[field]", "country.iso3"), ("filter[value]", cfg.get("iso3", "SOM")),
              ("limit", "500"), ("sort[]", "date.created:desc"),
              ("fields[include][]", "title"), ("fields[include][]", "url"), ("fields[include][]", "date"),
              ("fields[include][]", "source.name"), ("fields[include][]", "type.name")]
    import urllib.parse
    data = get_json(f"{API}?{urllib.parse.urlencode(params)}")
    notices = []
    for row in data.get("data", []):
        f = row.get("fields", {})
        types = [t.get("name", "") for t in f.get("type", [])]
        if cfg.get("consultancies_only", True) and not any("consult" in t.lower() for t in types):
            continue
        org = ", ".join(s.get("name", "") for s in f.get("source", []))
        notices.append({
            "source": "ReliefWeb", "source_id": str(row.get("id")), "title": clean(f.get("title")),
            "type": "Consultancy", "published": iso_date((f.get("date") or {}).get("created")),
            "deadline": iso_date((f.get("date") or {}).get("closing")), "deadline_time": "",
            "organization": org, "funder": "", "reference": "", "project_ids": [], "project_name": "",
            "method": "", "contact": {}, "url": f.get("url"), "description": "",
        })
    log(f"  ReliefWeb consultancies: {len(notices)}")
    return {"projects": [], "notices": notices, "news": []}
