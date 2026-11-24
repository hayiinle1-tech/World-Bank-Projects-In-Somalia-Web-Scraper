"""De-duplication engine.

The same project is often published by several organisations: the World Bank lists it,
the World Bank also reports it to IATI, the UN agency implementing it reports it again,
and the bilateral donor co-funding it reports it a fourth time. This module clusters
those records into ONE project, keeping links back to every source.

Two records are treated as the same project when:
  1. they share an identifier (World Bank P-number, AfDB P-code, IATI id, funder ref), or
  2. their titles are near-identical after normalisation, and their dates and IDs don't conflict.
Notices and news items are merged the same way (reference numbers / near-identical titles).
"""
from __future__ import annotations

import re
from collections import defaultdict
from difflib import SequenceMatcher

STOP = set("""a an and the of for in on to with by at from into under via phase project projects programme
program programmes support supporting somalia somali somaliland puntland federal republic government fgs
national regional ii iii iv""".split())
PREFIX = re.compile(r"^(?:[a-z0-9]{2,8}/){1,3}")          # e.g. "ROAF/SOM/"
NUMBERS = re.compile(r"\b(?:phase\s*)?(\d+|ii|iii|iv|v|vi)\b")
SOURCE_RANK = {"World Bank": 0, "IATI": 2}


class UnionFind:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def norm_title(title: str) -> str:
    t = PREFIX.sub("", (title or "").lower())
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return " ".join(w for w in t.split() if w not in STOP)


def _numbers(title: str) -> set[str]:
    return set(NUMBERS.findall((title or "").lower()))


def similar(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    ta, tb = set(a.split()), set(b.split())
    jac = len(ta & tb) / len(ta | tb)
    if jac < 0.5:
        return jac
    return max(jac, SequenceMatcher(None, a, b).ratio())


def _year(d):
    return int(d[:4]) if d else None


def _cluster(records: list[dict], keys_of, compatible, threshold: float, min_tokens: int = 3) -> list[list[dict]]:
    """Generic clustering: shared keys first, then fuzzy titles inside token blocks."""
    n = len(records)
    uf = UnionFind(n)

    # 1) exact identifier matches (ignore keys so common they would chain unrelated projects)
    by_key = defaultdict(list)
    for i, r in enumerate(records):
        for k in keys_of(r):
            by_key[k].append(i)
    for k, idx in by_key.items():
        if 1 < len(idx) <= 15:
            for j in idx[1:]:
                if compatible(records[idx[0]], records[j]):
                    uf.union(idx[0], j)

    # 2) fuzzy titles, compared only within blocks sharing a fairly rare word
    normed = [norm_title(r.get("title", "")) for r in records]
    blocks = defaultdict(list)
    for i, t in enumerate(normed):
        for w in set(t.split()):
            if len(w) > 3:
                blocks[w].append(i)
    seen = set()
    for w, idx in blocks.items():
        if len(idx) < 2 or len(idx) > 300:
            continue
        for x in range(len(idx)):
            for y in range(x + 1, len(idx)):
                a, b = idx[x], idx[y]
                if (a, b) in seen or uf.find(a) == uf.find(b):
                    continue
                seen.add((a, b))
                if len(normed[a].split()) < min_tokens or len(normed[b].split()) < min_tokens:
                    continue
                if _numbers(records[a].get("title")) != _numbers(records[b].get("title")):
                    continue  # "Phase II" is not "Phase III"
                if similar(normed[a], normed[b]) >= threshold and compatible(records[a], records[b]):
                    uf.union(a, b)

    groups = defaultdict(list)
    for i in range(n):
        groups[uf.find(i)].append(records[i])
    return list(groups.values())


# --------------------------------------------------------------------------- projects
def _project_keys(r):
    return {k.upper() for k in r.get("ids", []) if k}


def _project_compatible(a, b) -> bool:
    wa = {k for k in a.get("ids", []) if re.fullmatch(r"P\d{6}", k)}
    wb = {k for k in b.get("ids", []) if re.fullmatch(r"P\d{6}", k)}
    if wa and wb and not (wa & wb):
        return False  # two different World Bank projects
    ya, yb = _year(a.get("start")), _year(b.get("start"))
    return not (ya and yb and abs(ya - yb) > 3)


STATUS_ORDER = ["Active", "Pipeline", "Finalisation", "Suspended", "Closed", "Cancelled", "Dropped", ""]


def merge_projects(records: list[dict]) -> list[dict]:
    merged = []
    for group in _cluster(records, _project_keys, _project_compatible, threshold=0.88):
        group.sort(key=lambda r: (SOURCE_RANK.get(r["source"], 1), -len(r.get("description") or "")))
        lead = group[0]
        ids = sorted({k for r in group for k in r.get("ids", [])})
        wb = [k for k in ids if re.fullmatch(r"P\d{6}", k)]
        afdb = [k for k in ids if re.fullmatch(r"P-[A-Z]{2}-[A-Z0-9]{2,3}-\d{3}", k)]
        statuses = [r.get("status") or "" for r in group]
        status = min(statuses, key=lambda s: STATUS_ORDER.index(s) if s in STATUS_ORDER else 6) or "Unknown"
        starts = [r["start"] for r in group if r.get("start")]
        ends = [r["end"] for r in group if r.get("end")]
        merged.append({
            "id": (wb or afdb or [lead["source_id"]])[0],
            "title": re.sub(r"^(?:[A-Z0-9]{2,8}/){1,3}\s*", "", lead["title"]) or lead["title"],
            "description": max((r.get("description") or "" for r in group), key=len),
            "status": status,
            "funders": sorted({f for r in group for f in r.get("funders", []) if f}),
            "implementers": sorted({f for r in group for f in r.get("implementers", []) if f}),
            "start": min(starts) if starts else None,
            "end": max(ends) if ends else None,
            # max, not sum: several reports of the same money must not be double counted
            "commitment_usd": max((r.get("commitment_usd") or 0) for r in group),
            "sectors": sorted({s for r in group for s in r.get("sectors", [])}),
            "ids": ids,
            "url": lead.get("url"),
            "sources": [{"source": r["source"], "id": r["source_id"], "title": r["title"],
                         "funder": ", ".join(r.get("funders", [])), "url": r.get("url")} for r in group],
            "source_count": len(group),
        })
    merged.sort(key=lambda p: (p["status"] != "Active", -(p["commitment_usd"] or 0)))
    return merged


# --------------------------------------------------------------------------- notices
def _ref(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _notice_keys(r):
    keys = set()
    if len(_ref(r.get("reference"))) >= 6:
        keys.add("REF:" + _ref(r["reference"]))
    if r.get("url"):
        keys.add("URL:" + r["url"].split("#")[0].rstrip("/").lower())
    return keys


def _notice_compatible(a, b) -> bool:
    if a.get("deadline") and b.get("deadline") and a["deadline"] != b["deadline"]:
        # same tender re-advertised with a new deadline still counts; different years don't
        return a["deadline"][:4] == b["deadline"][:4]
    return True


def merge_notices(records: list[dict], previous: dict[str, str], today: str) -> list[dict]:
    merged = []
    for group in _cluster(records, _notice_keys, _notice_compatible, threshold=0.92, min_tokens=4):
        group.sort(key=lambda r: (SOURCE_RANK.get(r["source"], 1), r.get("published") or "9999"))
        lead = group[0]
        deadlines = [r["deadline"] for r in group if r.get("deadline")]
        published = [r["published"] for r in group if r.get("published")]
        keys = [r.get("url") or r.get("source_id") for r in group]
        seen = [previous[k] for k in keys if k in previous]
        # very first run: don't flag the whole back-catalogue as "new"
        first_seen = min(seen) if seen else (today if previous else (min(published) if published else today))
        merged.append({
            **{k: lead.get(k) for k in ("title", "type", "deadline_time", "organization", "funder",
                                       "reference", "project_name", "method", "contact", "url", "description")},
            "id": lead["source_id"],
            "published": min(published) if published else None,
            "deadline": max(deadlines) if deadlines else None,
            "project_ids": sorted({p for r in group for p in r.get("project_ids", []) if p}),
            "sources": [{"source": r["source"], "url": r.get("url")} for r in group],
            "first_seen": first_seen,
        })
    merged.sort(key=lambda n: n.get("published") or "", reverse=True)
    return merged


def merge_news(records: list[dict]) -> list[dict]:
    out = []
    for group in _cluster(records, lambda r: {"URL:" + (r.get("url") or "")}, lambda a, b: True,
                          threshold=0.85, min_tokens=3):
        group.sort(key=lambda r: r.get("published") or "")
        lead = group[0]
        out.append({**lead, "also_reported_by": sorted({r["publisher"] for r in group[1:]} - {lead["publisher"]})})
    out.sort(key=lambda n: n.get("published") or "", reverse=True)
    return out


FUNDER_ALIASES = {"afdb": "african development", "wb": "world bank", "eu": "european"}


def link(projects: list[dict], notices: list[dict]) -> None:
    """Attach notices to the merged project they belong to."""
    index = {k.upper(): p for p in projects for k in p["ids"]}
    for p in projects:
        p["notice_count"] = 0
    # fallback: a notice whose text contains a project's full (normalised) title
    titled = [(f" {norm_title(p['title'])} ", p) for p in projects if len(norm_title(p["title"]).split()) >= 3]
    titled.sort(key=lambda tp: (-len(tp[0]), tp[1]["status"] != "Active"))
    for n in notices:
        n["project_ref"] = None
        match = next((index[pid.upper()] for pid in n.get("project_ids", []) if pid.upper() in index), None)
        if not match:
            text = f" {norm_title(n.get('title', '') + ' ' + (n.get('description') or ''))} "
            cands = [p for t, p in titled if t in text]
            alias = FUNDER_ALIASES.get((n.get("funder") or "").lower(), (n.get("funder") or "").lower())
            if cands and alias:  # same title? prefer the project of the notice's funder
                cands.sort(key=lambda p: alias not in " ".join(p["funders"]).lower())
            match = cands[0] if cands else None
        if match:
            n["project_ref"] = match["id"]
            n["project_name"] = n.get("project_name") or match["title"]
            match["notice_count"] += 1
