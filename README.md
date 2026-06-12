# BIV Portfolio Jobs Board

A self-hosted jobs board for the Burnt Island Ventures portfolio, working the same way Getro does: it pulls live job postings directly from each portfolio company's applicant tracking system (ATS) via their public JSON APIs. No scraping, no API keys, no manual entry for companies with a supported ATS.

## How it works

`companies.json` lists every portfolio company. For companies with a known ATS (Greenhouse, Lever, Ashby, Workable, Recruitee, or Breezy), `fetch_jobs.py` pulls their live openings and writes everything to `jobs.json`. `index.html` is a single-file static page that renders `jobs.json` with search and filters. Companies without a detected ATS still appear on the "All companies" tab with a link to their careers page.

## Try it locally

```
cd biv-jobs-board
python3 -m http.server 8000
```

Open http://localhost:8000 — it ships with live CivilGrid data (14 roles, fetched from their Ashby API) plus Floodbase's open role, so you can see exactly how it will look.

To refresh the data: `pip install requests` then `python3 fetch_jobs.py`.

## Current ATS coverage

As of June 2026, probing found: CivilGrid → Ashby (confirmed, 14 live roles). Other companies' ATSs weren't directly identifiable, so their `ats` field in `companies.json` is `null`.

## Scraping fallback

Companies with `ats: null` are scraped automatically from their careers page, in three layers: (1) detect an embedded or linked ATS in the page HTML (Greenhouse/Lever/Ashby/Workable/Recruitee/Breezy embeds) and switch to its clean API; (2) parse schema.org JobPosting markup, which many sites include for Google Jobs; (3) with the `--render` flag, execute the page's JavaScript via Playwright first — this catches client-rendered careers pages like SewerAI's. For `--render`: `pip install playwright && playwright install chromium`. The GitHub Actions workflow already runs with `--render`.

If all three layers find nothing, the company still appears on the board with a careers-page link, so nothing silently disappears. Scraping is inherently less reliable than a configured ATS — when you learn a company's ATS, set `"ats"`/`"slug"` in `companies.json` and that company becomes rock-solid.

Note on LinkedIn: this project deliberately does not scrape LinkedIn. Automated scraping violates LinkedIn's terms of service and is technically blocked; careers pages and ATS APIs are the legitimate sources for the same data.

## Deploying (free, ~30 minutes)

1. Create a GitHub repo and push these files.
2. Move `update-jobs.yml` to `.github/workflows/update-jobs.yml` — this refreshes `jobs.json` every night automatically.
3. Enable GitHub Pages (Settings → Pages → deploy from branch).
4. Point a subdomain at it, e.g. `jobs.burntislandventures.com` (add a CNAME in your DNS pointing to `<username>.github.io`, and set the custom domain in Pages settings).
5. Link to it from the existing Jobs Board nav item on burntislandventures.com.

Alternative hosts that work identically: Netlify, Vercel, Cloudflare Pages.

## Squarespace note

Your main site is on Squarespace. Squarespace can't run the nightly fetcher, so don't try to host the board inside Squarespace itself — host it on the subdomain and link to it (this is exactly what Imagine H2O does: their board lives at watertechjobs.imagineh2o.org, separate from imagineh2o.org). You could also embed it via a code block + iframe, but a subdomain is cleaner.

## Adding a company or ATS

Add a line to `companies.json`. Supported `ats` values: `greenhouse`, `lever`, `ashby`, `workable`, `recruitee`, `breezy`. The slug is the company identifier in their job board URL, e.g. `jobs.ashbyhq.com/civilgrid` → slug `civilgrid`; `boards.greenhouse.io/acme` → slug `acme`.
