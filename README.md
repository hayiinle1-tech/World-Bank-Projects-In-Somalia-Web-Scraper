# Somalia Projects & Tenders Tracker

A free, self-updating website that collects **development projects and tenders in Somalia from many sources across the internet**, **merges duplicates into one record per project**, and republishes itself on GitHub Pages **every 6 hours**.

## Sources (all free, no paid data)

| Source | What it adds | Key needed? |
|---|---|---|
| **World Bank Search API** | All Somalia projects + every procurement notice (EOIs, bids, awards) | No |
| **IATI via D-Portal** | ~5,000 active/pipeline projects published by 1,000+ funders: AfDB, UNDP, UNICEF, WFP, FAO, IOM, EU, USAID, FCDO, Germany, Sweden, Norway, TIKA, NGOs… | No |
| **AfDB procurement RSS** | AfDB project procurement notices, filtered to Somalia | No |
| **Google News RSS** (3 searches) | News signals across the web: new financing, tenders, contracts, investments | No |
| **Any RSS/Atom feed you add** | Ministries, NGOs, UN agencies, local news — anything with a feed | No |
| **ReliefWeb** (optional) | Consultancy opportunities in Somalia | Free approved `appname` |

Add or remove sources by editing **`sources.json`** — no code changes needed. For example, to add a feed:

```json
{ "name": "My source", "url": "https://example.org/feed.xml", "kind": "auto", "keywords": ["somalia", "mogadishu"] }
```

`kind` is `notices` (tenders), `news`, or `auto` (classified by wording such as tender, RFQ, EOI, bid, procurement).

## How duplicates are merged

The same project is often published 2–5 times (the World Bank lists it, reports it again to IATI, the UN agency implementing it reports it, and the co-funder reports it too). `scraper/merge.py` clusters these into **one project**:

1. **Shared identifiers** — World Bank `P123456`, AfDB `P-SO-XXX-001`, IATI IDs and funder references linking an implementer's record to its donor's record.
2. **Near-identical titles** — after removing noise (agency prefixes like `ROAF/SOM/`, words like "Somalia", "project", "programme"), with safety checks: start dates must be within 3 years, different World Bank IDs never merge, and "Phase II" never merges with "Phase III".

Each merged project keeps links to **every source record**, takes the **largest** commitment (never the sum, so money isn't double counted), and lists all funders. Tenders are merged the same way (reference numbers and URLs), then linked to their project. Identical news stories from different outlets become one item.

## Files

```
index.html                     the website (plain HTML/JS, no build step)
sources.json                   which sources to scrape, plus your own RSS feeds
scraper/run.py                 main entry: fetch → merge → write data/
scraper/merge.py               de-duplication engine
scraper/sources/*.py           one module per source type
data/*.json                    generated: projects, notices, news, meta
.github/workflows/scrape.yml   runs every 6 hours + deploys to GitHub Pages
```

## Deploy on GitHub

1. Create a new public repository and upload everything in this folder, including the `.github` folder.
2. **Settings → Pages → Source:** choose **GitHub Actions**.
3. **Settings → Actions → General → Workflow permissions:** choose **Read and write permissions**.
4. **Actions** tab → **Scrape & deploy** → **Run workflow**.

The site goes live at `https://<username>.github.io/<repo>/` and refreshes itself every 6 hours (03:23, 09:23, 15:23, 21:23 Mogadishu time). GitHub may delay scheduled runs by a few minutes when it's busy.

**Optional: ReliefWeb.** Request a free appname at https://apidoc.reliefweb.int/, then add it under **Settings → Secrets and variables → Actions → New repository secret**, named `RELIEFWEB_APPNAME`.

## Run locally

```bash
python scraper/run.py                     # all sources
python scraper/run.py --only worldbank    # one source
python -m http.server 8000                # open http://localhost:8000
```

Python 3.9+ standard library only — nothing to install.

## Use the data in other tools

The JSON files are public once deployed. You can use them in n8n, Airtable, Google Sheets or an AI agent:

```
https://<username>.github.io/<repo>/data/projects.json
https://<username>.github.io/<repo>/data/notices.json   (has "first_seen" for new-tender alerts)
https://<username>.github.io/<repo>/data/news.json
```

## Notes

- If one source fails, the others still run; the site footer shows which sources succeeded in the last run.
- If every source fails, the previous data is kept and still deployed.
- This is an unofficial tracker. Always confirm deadlines on the original notice before bidding.
