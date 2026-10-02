# BIV Portfolio Jobs Board

A self-hosted jobs board for the Burnt Island Ventures portfolio. It pulls current job postings from public applicant tracking systems and selected employer careers pages, then publishes a static board.

## How it works

`companies.json` lists portfolio companies. `fetch_jobs.py` pulls public ATS feeds and selected employer careers pages into `jobs.json`. `index.html` renders the data with search and filters. Companies without verified openings still appear on the “All companies” tab with a careers link.

## Try it locally

```
cd biv-jobs-board
pip install requests
python -m unittest discover -s tests -v
python fetch_jobs.py
python -m http.server 8000
```

Open http://localhost:8000 to see the latest generated data.

## Coverage and diagnostics

The GitHub Actions workflow runs nightly and whenever the importer, configuration, tests, or workflow changes on `main`. It runs tests before refreshing. `jobs.json` records each company’s `source_status`: `ok`, `unverified`, `disabled`, `unsupported`, `error_stale`, or `error_no_prior` (plus `unsupported_stale` when applicable). It also lists fetch errors and companies with stale, unverified, disabled, or unsupported sources. If a fetch fails, previously published roles are retained and the workflow logs a warning. A successful zero-job response clears prior roles; a careers page without structured listings is marked unverified rather than confirmed empty.

Companies with `ats: null` are checked for an embedded ATS or schema.org JobPosting markup. Local `--render` support can run Playwright for JavaScript pages, but the production workflow runs without it. Prefer a direct ATS configuration when its board is verified. Floodbase and Waterly have dedicated parsers for current listings on their careers pages. SwiftComply uses public Rippling board links; an unreadable board is reported as an error rather than as zero openings.

The project does not scrape LinkedIn. A role found only on LinkedIn, such as the currently observed AlgaFilm listing, remains unverified in the automatic board until an employer-controlled source or reviewed manual workflow is available.

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

Add a line to `companies.json`. Supported `ats` values: `greenhouse`, `lever`, `ashby`, `workable`, `recruitee`, `breezy`, `bamboohr`, `gusto`, `rippling`, and the source-specific `floodbase` and `waterly`. The slug is the company identifier in their job board URL, e.g. `jobs.ashbyhq.com/civilgrid` → slug `civilgrid`; `boards.greenhouse.io/acme` → slug `acme`.
