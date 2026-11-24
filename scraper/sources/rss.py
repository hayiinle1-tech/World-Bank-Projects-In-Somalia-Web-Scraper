"""Generic RSS / Atom source. Works with ANY feed on the internet.

Each feed in sources.json can set:
  url          feed address (required)
  name         label shown on the website
  keywords     only keep items mentioning at least one of these (e.g. Somalia, Mogadishu)
  kind         "notices" (tenders), "news", or "auto" (classify each item by its wording)
  funder       optional funder name for notices (e.g. "AfDB")
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from common import clean, extract_ids, http_get, iso_date, log, looks_like_tender


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _items(xml: bytes) -> list[dict]:
    root = ET.fromstring(xml)
    out = []
    for el in root.iter():
        if _strip_ns(el.tag) not in ("item", "entry"):
            continue
        rec = {}
        for child in el:
            t = _strip_ns(child.tag)
            if t == "link":
                rec.setdefault("link", child.get("href") or (child.text or "").strip())
            elif t in ("title", "description", "summary", "content", "pubdate", "published", "updated",
                       "date", "guid", "id", "source", "creator"):
                rec.setdefault(t, (child.text or "").strip())
        out.append(rec)
    return out


def fetch_feed(feed: dict) -> dict:
    name = feed.get("name") or feed["url"]
    keywords = [k.lower() for k in feed.get("keywords", [])]
    kind = feed.get("kind", "auto")
    result = {"projects": [], "notices": [], "news": []}
    for it in _items(http_get(feed["url"], timeout=45)):
        title = clean(it.get("title"))
        summary = clean(it.get("description") or it.get("summary") or it.get("content"), 400)
        text = f"{title} {summary}".lower()
        if keywords and not any(re.search(rf"\b{re.escape(k)}", text) for k in keywords):
            continue
        link = it.get("link") or it.get("guid") or it.get("id")
        published = iso_date(it.get("pubdate") or it.get("published") or it.get("updated") or it.get("date"))
        publisher = clean(it.get("source")) or name
        is_tender = kind == "notices" or (kind == "auto" and looks_like_tender(title))
        if is_tender:
            ref_match = re.search(r"\b(?:ref(?:erence)?(?: no)?[.:]?\s*)([A-Z0-9][A-Z0-9/_.-]{4,})", f"{title} {summary}", re.I)
            result["notices"].append({
                "source": name, "source_id": link, "title": title, "type": _guess_type(title),
                "published": published, "deadline": _guess_deadline(summary), "deadline_time": "",
                "organization": publisher, "funder": feed.get("funder", ""),
                "reference": ref_match.group(1).rstrip("./-_") if ref_match else "",
                "project_ids": sorted(extract_ids(title, summary)), "project_name": "",
                "method": "", "contact": {}, "url": link, "description": summary,
            })
        else:
            result["news"].append({"source": name, "title": title, "url": link, "published": published,
                                   "publisher": publisher, "summary": summary})
    log(f"  RSS {name}: {len(result['notices'])} notices, {len(result['news'])} news")
    return result


def _guess_type(title: str) -> str:
    t = title.lower()
    for pat, label in ((r"expression|eoi|\bami\b", "Request for Expression of Interest"),
                       (r"\brfq\b|quotation", "Request for Quotation"),
                       (r"\brfp\b|proposal", "Request for Proposals"),
                       (r"\bitb\b|invitation (to|for) bid|appel d.offres|\bao\b", "Invitation for Bids"),
                       (r"award|attribution", "Contract Award"),
                       (r"\bgpn\b|general procurement", "General Procurement Notice"),
                       (r"\bppm\b|procurement plan|plan de passation", "Procurement Plan")):
        if re.search(pat, t):
            return label
    return "Notice"


def _guess_deadline(text: str) -> str | None:
    m = re.search(r"(?:deadline|closing date|submission[^.]{0,30}?(?:by|before|on))[^0-9]{0,20}"
                  r"(\d{1,2}[ -](?:\w{3,9})[ -,]*\d{4}|\w{3,9} \d{1,2},? \d{4}|\d{4}-\d{2}-\d{2})", text or "", re.I)
    return iso_date(m.group(1).replace(",", "")) if m else None


def fetch(cfg: dict) -> dict:
    merged = {"projects": [], "notices": [], "news": []}
    for feed in cfg.get("feeds", []):
        if feed.get("enabled", True) is False:
            continue
        try:
            part = fetch_feed(feed)
            for k in merged:
                merged[k].extend(part[k])
        except Exception as e:  # one broken feed must not stop the others
            log(f"  ! RSS {feed.get('name') or feed.get('url')} failed: {e}")
    return merged
