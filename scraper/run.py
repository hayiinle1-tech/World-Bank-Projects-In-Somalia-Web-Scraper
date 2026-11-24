#!/usr/bin/env python3
"""Somalia projects & tenders tracker — main entry point.

Reads sources.json, pulls every enabled source, merges duplicates into single
projects / notices, and writes data/*.json for the website.

    python scraper/run.py                 # all enabled sources
    python scraper/run.py --only worldbank,rss
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import log, now_iso, today  # noqa: E402
from merge import link, merge_news, merge_notices, merge_projects  # noqa: E402
from sources import iati, reliefweb, rss, worldbank  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SOURCES = {"worldbank": worldbank, "iati": iati, "rss": rss, "reliefweb": reliefweb}


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(name: str, payload) -> None:
    DATA.mkdir(exist_ok=True)
    p = DATA / name
    p.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"  wrote data/{name} ({p.stat().st_size / 1024:.0f} KB)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "sources.json"))
    ap.add_argument("--only", help="comma-separated source keys to run")
    args = ap.parse_args()

    config = load_json(Path(args.config), {})
    only = set(args.only.split(",")) if args.only else None
    raw = {"projects": [], "notices": [], "news": []}
    status = []

    for key, cfg in config.get("sources", {}).items():
        if (only and key not in only) or not cfg.get("enabled", True) or key not in SOURCES:
            continue
        log(f"→ {key}")
        t0 = time.time()
        try:
            part = SOURCES[key].fetch({**config.get("defaults", {}), **cfg})
            for k in raw:
                raw[k].extend(part.get(k, []))
            status.append({"source": key, "ok": True, "seconds": round(time.time() - t0, 1),
                           **{k: len(part.get(k, [])) for k in raw}})
        except Exception as e:  # keep going if one source is down
            log(f"  ! {key} failed: {e}")
            status.append({"source": key, "ok": False, "error": str(e)[:300]})

    if not raw["projects"] and not raw["notices"]:
        log("Nothing fetched from any source — keeping previous data.")
        return 1

    # remember when each notice was first seen, so the site can flag new tenders
    previous = {}
    for n in load_json(DATA / "notices.json", []):
        for s in n.get("sources", []):
            if s.get("url"):
                previous[s["url"]] = n.get("first_seen") or today()

    log("→ merging duplicates")
    projects = merge_projects(raw["projects"]) if raw["projects"] else load_json(DATA / "projects.json", [])
    notices = merge_notices(raw["notices"], previous, today())
    news = merge_news(raw["news"])
    link(projects, notices)

    t = today()
    meta = {
        "updated_at": now_iso(),
        "country": config.get("defaults", {}).get("country_code", "SO"),
        "raw_records": {k: len(v) for k, v in raw.items()},
        "project_count": len(projects),
        "duplicates_merged": len(raw["projects"]) - len(projects) + len(raw["notices"]) - len(notices),
        "multi_source_projects": sum(1 for p in projects if p["source_count"] > 1),
        "active_projects": sum(1 for p in projects if p["status"] == "Active"),
        "total_commitment_usd": sum(p["commitment_usd"] or 0 for p in projects if p["status"] in ("Active", "Pipeline")),
        "notice_count": len(notices),
        "open_notices": sum(1 for n in notices if n.get("deadline") and n["deadline"] >= t),
        "new_notices_today": sum(1 for n in notices if n.get("first_seen", "") >= t) if previous else 0,
        "news_count": len(news),
        "sources": status,
    }
    write_json("projects.json", projects)
    write_json("notices.json", notices)
    write_json("news.json", news)
    write_json("meta.json", meta)
    log(f"Done: {len(raw['projects'])} project records → {len(projects)} projects; "
        f"{len(raw['notices'])} notices → {len(notices)}; {len(news)} news items.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
