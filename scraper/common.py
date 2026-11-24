"""Shared helpers: HTTP, dates, text cleaning, identifier extraction."""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape

USER_AGENT = "Mozilla/5.0 (compatible; somalia-projects-tracker/2.0; +https://github.com)"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- HTTP
def http_get(url: str, params: dict | None = None, retries: int = 3, timeout: int = 60) -> bytes:
    if params:
        url = f"{url}{'&' if '?' in url else '?'}{urllib.parse.urlencode(params, safe='|,')}"
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
            if isinstance(e, urllib.error.HTTPError) and e.code in (400, 401, 403, 404):
                break
            time.sleep(2 ** attempt)
    raise RuntimeError(f"GET failed {url}: {last}")


def get_json(url: str, params: dict | None = None, **kw):
    return json.loads(http_get(url, params, **kw).decode("utf-8"))


# --------------------------------------------------------------------------- dates
_FORMATS = ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d",
            "%m/%d/%Y %I:%M:%S %p", "%d-%b-%Y", "%d-%b-%y", "%m/%d/%Y", "%d %B %Y", "%B %d, %Y")


def iso_date(value) -> str | None:
    """Normalise many date formats (and IATI day-numbers) to YYYY-MM-DD."""
    if value in (None, "", 0):
        return None
    if isinstance(value, (int, float)):  # D-Portal: days since 1970-01-01
        try:
            return (date(1970, 1, 1) + timedelta(days=int(value))).isoformat()
        except OverflowError:
            return None
    s = str(value).strip()
    for fmt in _FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    try:
        return parsedate_to_datetime(s).date().isoformat()  # RFC-822 (RSS pubDate)
    except (TypeError, ValueError, IndexError):
        pass
    m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else None


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- text
def clean(value, limit: int | None = None) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value if v)
    text = unescape(unescape(str(value)))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0] + "…"
    return text


def num(value) -> float:
    try:
        return float(str(value).replace(",", "").strip()) if value not in (None, "") else 0.0
    except ValueError:
        return 0.0


# --------------------------------------------------------------------------- identifiers
WB_ID = re.compile(r"\bP\d{6}\b")                       # World Bank project ID, e.g. P501988
AFDB_ID = re.compile(r"\bP-[A-Z]{2}-[A-Z0-9]{2,3}-\d{3}\b")  # AfDB SAP code, e.g. P-SO-AAZ-001


def extract_ids(*texts) -> set[str]:
    """Find well-known project identifiers inside any text (titles, IATI ids, refs)."""
    found: set[str] = set()
    for t in texts:
        if not t:
            continue
        s = str(t).upper()
        found.update(WB_ID.findall(s))
        found.update(AFDB_ID.findall(s))
    return found


TENDER_WORDS = re.compile(
    r"\b(tender|bid|bids|bidding|rfq|rfp|itb|eoi|expressions? of interest|request for (?:quotation|proposals?)|"
    r"procurement|invitation to|call for (?:proposals|applications)|consultancy|consultant|"
    r"appel d.offres|ami|avis|contract award|prequalification|supply of|supply and delivery)\b", re.I)


def looks_like_tender(text: str) -> bool:
    return bool(TENDER_WORDS.search(text or ""))
