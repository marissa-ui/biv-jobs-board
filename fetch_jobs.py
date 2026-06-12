#!/usr/bin/env python3
"""
BIV Portfolio Jobs Board - job fetcher.

Reads companies.json, pulls live job postings from each company's ATS
public API (the same trick Getro uses), and writes jobs.json for the
static frontend (index.html).

Supported ATSs: Greenhouse, Lever, Ashby, Workable, Recruitee, Breezy.
No API keys needed - these are all public endpoints.

Usage:  python3 fetch_jobs.py
Deps:   pip install requests
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

HERE = Path(__file__).parent
TIMEOUT = 20
HEADERS = {"User-Agent": "BIV-Jobs-Board/1.0 (jobs.burntislandventures.com)"}


def get_json(url, method="GET"):
    r = requests.request(method, url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def fetch_greenhouse(slug):
    data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    return [
        {
            "title": j["title"],
            "location": (j.get("location") or {}).get("name", ""),
            "department": ", ".join(d["name"] for d in j.get("departments", []) if d.get("name")),
            "url": j["absolute_url"],
            "posted_at": j.get("updated_at", ""),
        }
        for j in data.get("jobs", [])
    ]


def fetch_lever(slug):
    data = get_json(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    return [
        {
            "title": j["text"],
            "location": (j.get("categories") or {}).get("location", ""),
            "department": (j.get("categories") or {}).get("team", ""),
            "url": j["hostedUrl"],
            "posted_at": datetime.fromtimestamp(j["createdAt"] / 1000, tz=timezone.utc).isoformat()
            if j.get("createdAt") else "",
        }
        for j in data
    ]


def fetch_ashby(slug):
    data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    jobs = []
    for j in data.get("jobs", []):
        if not j.get("isListed", True):
            continue
        locations = [j.get("location", "")] + [
            s.get("location", "") for s in j.get("secondaryLocations", [])
        ]
        jobs.append(
            {
                "title": j["title"],
                "location": " / ".join(l for l in locations if l),
                "department": j.get("department", "") or j.get("team", ""),
                "url": j.get("jobUrl", ""),
                "posted_at": j.get("publishedAt", ""),
            }
        )
    return jobs


def fetch_workable(slug):
    data = get_json(f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=false")
    return [
        {
            "title": j["title"],
            "location": ", ".join(
                p for p in [(j.get("city") or ""), (j.get("country") or "")] if p
            ) or ("Remote" if j.get("telecommuting") else ""),
            "department": j.get("department", ""),
            "url": j["url"],
            "posted_at": j.get("published_on", ""),
        }
        for j in data.get("jobs", [])
    ]


def fetch_recruitee(slug):
    data = get_json(f"https://{slug}.recruitee.com/api/offers/")
    return [
        {
            "title": j["title"],
            "location": j.get("location", ""),
            "department": j.get("department", "") or "",
            "url": j["careers_url"],
            "posted_at": j.get("published_at", ""),
        }
        for j in data.get("offers", [])
    ]


def fetch_breezy(slug):
    data = get_json(f"https://{slug}.breezy.hr/json")
    return [
        {
            "title": j["name"],
            "location": (j.get("location") or {}).get("name", ""),
            "department": j.get("department", ""),
            "url": j["url"],
            "posted_at": j.get("published_date", ""),
        }
        for j in data
    ]


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "workable": fetch_workable,
    "recruitee": fetch_recruitee,
    "breezy": fetch_breezy,
}

# ---------------------------------------------------------------------------
# Careers-page scraping fallback (used when ats is null in companies.json)
# ---------------------------------------------------------------------------

import re

# If a careers page embeds or links an ATS, we detect it and use the clean API.
ATS_URL_PATTERNS = {
    "greenhouse": r"(?:boards|job-boards|boards-api)\.greenhouse\.io/(?:v1/boards/)?([A-Za-z0-9_-]+)",
    "lever":      r"jobs\.lever\.co/([A-Za-z0-9_-]+)",
    "ashby":      r"jobs\.ashbyhq\.com/([A-Za-z0-9_-]+)",
    "workable":   r"apply\.workable\.com/([A-Za-z0-9_-]+)",
    "recruitee":  r"https?://([A-Za-z0-9-]+)\.recruitee\.com",
    "breezy":     r"https?://([A-Za-z0-9-]+)\.breezy\.hr",
}
SLUG_BLOCKLIST = {"api", "www", "embed", "j", "jobs", "careers"}


def get_html(url, render=False):
    """Fetch page HTML. With render=True, use Playwright to execute JS
    (needed for client-rendered careers pages). pip install playwright &&
    playwright install chromium"""
    if render:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto(url, wait_until="networkidle", timeout=45000)
            html = page.content()
            browser.close()
            return html
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


def detect_ats(html):
    """Return (ats, slug) if the page links/embeds a known ATS, else None."""
    for ats, pattern in ATS_URL_PATTERNS.items():
        for slug in re.findall(pattern, html):
            if slug.lower() not in SLUG_BLOCKLIST:
                return ats, slug
    return None


def parse_jsonld_jobs(html, base_url):
    """Extract schema.org JobPosting items (used by sites for Google Jobs)."""
    jobs = []
    for block in re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE,
    ):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data])
        for item in items:
            if not isinstance(item, dict) or item.get("@type") != "JobPosting":
                continue
            loc = item.get("jobLocation") or {}
            if isinstance(loc, list):
                loc = loc[0] if loc else {}
            addr = loc.get("address") or {}
            location = ", ".join(
                p for p in [addr.get("addressLocality"), addr.get("addressRegion")] if p
            ) or ("Remote" if item.get("jobLocationType") == "TELECOMMUTE" else "")
            jobs.append({
                "title": item.get("title", "").strip(),
                "location": location,
                "department": "",
                "url": item.get("url") or item.get("hiringOrganization", {}).get("sameAs") or base_url,
                "posted_at": item.get("datePosted", ""),
            })
    return [j for j in jobs if j["title"]]


def fetch_scraped(careers_url, render=False):
    """Fallback for companies with no configured ATS:
    1. detect an embedded/linked ATS and use its API
    2. else parse schema.org JobPosting markup
    3. with render=True, retry both after executing the page's JS"""
    html = get_html(careers_url)
    detected = detect_ats(html)
    if detected:
        ats, slug = detected
        try:
            return FETCHERS[ats](slug), f"detected {ats}:{slug}"
        except Exception:
            pass
    jobs = parse_jsonld_jobs(html, careers_url)
    if jobs:
        return jobs, "json-ld"
    if render:
        html = get_html(careers_url, render=True)
        detected = detect_ats(html)
        if detected:
            ats, slug = detected
            return FETCHERS[ats](slug), f"detected {ats}:{slug} (rendered)"
        jobs = parse_jsonld_jobs(html, careers_url)
        if jobs:
            return jobs, "json-ld (rendered)"
    return [], "no structured jobs found"


def main():
    render = "--render" in sys.argv  # JS rendering via Playwright
    config = json.loads((HERE / "companies.json").read_text())
    out_companies = []
    total = 0
    errors = []

    for c in config["companies"]:
        entry = {
            "name": c["name"],
            "website": c["website"],
            "careers_url": c.get("careers_url") or c["website"],
            "jobs": [],
        }
        ats = c.get("ats")
        if ats:
            try:
                entry["jobs"] = FETCHERS[ats](c["slug"])
                total += len(entry["jobs"])
                print(f"  {c['name']:<20} {ats:<12} {len(entry['jobs'])} jobs")
            except Exception as e:
                errors.append(f"{c['name']} ({ats}/{c['slug']}): {e}")
                print(f"  {c['name']:<20} {ats:<12} ERROR: {e}", file=sys.stderr)
        else:
            try:
                jobs, how = fetch_scraped(entry["careers_url"], render=render)
                entry["jobs"] = jobs
                total += len(jobs)
                print(f"  {c['name']:<20} {'scrape':<12} {len(jobs)} jobs ({how})")
            except Exception as e:
                errors.append(f"{c['name']} (scrape): {e}")
                print(f"  {c['name']:<20} {'scrape':<12} ERROR: {e}", file=sys.stderr)
        out_companies.append(entry)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_jobs": total,
        "companies": out_companies,
    }
    (HERE / "jobs.json").write_text(json.dumps(output, indent=2))
    print(f"\nWrote jobs.json - {total} jobs across "
          f"{sum(1 for c in out_companies if c['jobs'])} companies.")
    if errors:
        print(f"{len(errors)} fetch errors (companies kept with careers link only).")


if __name__ == "__main__":
    main()
