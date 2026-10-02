#!/usr/bin/env python3
"""
BIV Portfolio Jobs Board - job fetcher.

Reads companies.json, pulls live job postings from each company's ATS
public API (the same trick Getro uses), and writes jobs.json for the
static frontend (index.html).

Supported ATSs: Greenhouse, Lever, Ashby, Workable, Recruitee, Breezy, Gusto,
BambooHR, and Rippling. Floodbase and Waterly use source-specific parsers.
No API keys needed - these are all public endpoints (Gusto is parsed from
its public, server-rendered board page).

Usage:  python3 fetch_jobs.py
Deps:   pip install requests
"""

import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

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


def fetch_bamboohr(slug):
    """BambooHR public board. The board page itself is client-rendered, but
    /careers/list serves the same postings as JSON. Location arrives in either
    `location` or `atsLocation`, and neither carries a posting date."""
    data = get_json(f"https://{slug}.bamboohr.com/careers/list")
    jobs = []
    for j in data.get("result", []):
        loc = j.get("location") or {}
        ats = j.get("atsLocation") or {}
        parts = [
            loc.get("city") or ats.get("city"),
            loc.get("state") or ats.get("state") or ats.get("province"),
        ]
        location = ", ".join(p for p in parts if p)
        if not location and j.get("isRemote"):
            location = "Remote"
        jobs.append({
            "title": j.get("jobOpeningName", "").strip(),
            "location": location,
            "department": j.get("departmentLabel", "") or "",
            "url": f"https://{slug}.bamboohr.com/careers/{j['id']}",
            "posted_at": "",
        })
    return [j for j in jobs if j["title"]]


def _parse_gusto(html):
    """Parse postings out of a Gusto public board page (server-rendered HTML).
    Each posting is an <a href="/postings/..."> wrapping an <h3> title and
    one or more <p> lines (first = location, second = employment type)."""
    jobs = []
    for m in re.finditer(r'<a[^>]+href="(/postings/[^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL):
        href, inner = m.group(1), m.group(2)
        tm = re.search(r'<h3[^>]*>(.*?)</h3>', inner, re.DOTALL)
        if not tm:
            continue
        title = re.sub(r'<[^>]+>', '', tm.group(1)).replace('&amp;', '&').strip()
        texts = []
        for p in re.findall(r'<p[^>]*>(.*?)</p>', inner, re.DOTALL):
            t = re.sub(r'<[^>]+>', ' ', p).replace('&amp;', '&')
            t = re.sub(r'\s+', ' ', t).strip()
            if t:
                texts.append(t)
        jobs.append({
            "title": title,
            "location": texts[0] if texts else "",
            "department": "",
            "url": "https://jobs.gusto.com" + href,
            "posted_at": "",
        })
    return jobs


def fetch_gusto(slug):
    """slug is the full Gusto board id from jobs.gusto.com/boards/<slug>."""
    url = f"https://jobs.gusto.com/boards/{slug}"
    jobs = _parse_gusto(get_html(url))
    if not jobs:  # rare; fall back to a rendered fetch if available
        try:
            jobs = _parse_gusto(get_html(url, render=True))
        except Exception:
            pass
    return jobs


class _FloodbaseLinks(HTMLParser):
    """Collect application links and their visible text from Floodbase's careers page."""

    def __init__(self):
        super().__init__()
        self.links = []
        self.current = None
        self.title_depth = 0
        self.title_parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href", "")
            parsed = urlparse(href)
            if parsed.netloc.lower() in {"tally.so", "www.tally.so"} and parsed.path.startswith("/r/"):
                clean_url = urlunparse(("https", "tally.so", parsed.path.rstrip("/"), "", "", ""))
                self.current = {"url": clean_url, "parts": [], "titles": []}
        elif self.current is not None:
            if self.title_depth:
                self.title_depth += 1
            elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"} or any(
                token in dict(attrs).get("class", "").lower()
                for token in ("job-title", "role-title", "position-title")
            ):
                self.title_depth = 1
                self.title_parts = []

    def handle_data(self, data):
        if self.current is not None:
            value = " ".join(data.split())
            if value:
                self.current["parts"].append(value)
                if self.title_depth:
                    self.title_parts.append(value)

    def handle_endtag(self, tag):
        if self.current is None:
            return
        if tag == "a":
            self.links.append(self.current)
            self.current = None
            self.title_depth = 0
        elif self.title_depth:
            self.title_depth -= 1
            if not self.title_depth and self.title_parts:
                self.current["titles"].append(" ".join(self.title_parts))


def fetch_floodbase(_slug=None):
    """Floodbase lists its current roles as Tally application links.

    Its footer also links to an older Greenhouse board, so ATS auto-detection
    cannot reliably identify the roles on the employer's current careers page.
    """
    parser = _FloodbaseLinks()
    parser.feed(get_html("https://www.floodbase.com/careers"))
    jobs = []
    seen = set()
    employment = re.compile(r"\b(?:full[ -]?time|part[ -]?time|contract|internship|temporary)\b", re.I)
    work_modes = {"hybrid", "remote", "on-site", "onsite"}
    for link in parser.links:
        parts = link["parts"]
        if not employment.search(" ".join(parts)) or link["url"] in seen:
            continue
        # Prefer the card's heading/title node. A text-only card can also place
        # the role immediately after its employment-type label.
        title = next((t for t in link["titles"] if not employment.fullmatch(t)), "")
        if not title:
            for index, part in enumerate(parts):
                if employment.fullmatch(part) and index + 1 < len(parts):
                    title = parts[index + 1]
                    break
        if not title:
            raise ValueError(f"Floodbase job card has no readable title: {link['url']}")
        position = parts.index(title) if title in parts else -1
        location = ""
        if position >= 0:
            location = next((p for p in parts[position + 1:] if p.lower() not in work_modes), "")
        type_index = next((i for i, p in enumerate(parts) if employment.fullmatch(p)), 0)
        department = parts[type_index - 1] if type_index > 0 else ""
        seen.add(link["url"])
        jobs.append({
            "title": title,
            "location": location,
            "department": department,
            "url": link["url"],
            "posted_at": "",
        })
    return jobs


class _RipplingLinks(HTMLParser):
    """Read visible public job links from a Rippling board's HTML."""

    def __init__(self, slug):
        super().__init__()
        self.slug = slug
        self.department = ""
        self.heading = None
        self.link = None
        self.jobs = []
        self.text = []
        self.last_job = None
        self.skip_text = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"style", "script"}:
            self.skip_text += 1
            return
        if self.skip_text:
            return
        if tag in {"h2", "h3"}:
            self.heading = []
        if tag == "a":
            href = dict(attrs).get("href", "")
            url = urljoin("https://ats.rippling.com/", href)
            parsed = urlparse(url)
            if parsed.netloc == "ats.rippling.com" and re.search(
                rf"/(?:[a-z]{{2}}-[A-Z]{{2}}/)?{re.escape(self.slug)}/jobs/[0-9a-f-]{{36}}/?$",
                parsed.path,
            ):
                if self.last_job and self.last_job["url"] != urlunparse(("https", "ats.rippling.com", parsed.path.rstrip("/"), "", "", "")):
                    self.last_job = None
                self.link = {"url": urlunparse(("https", "ats.rippling.com", parsed.path.rstrip("/"), "", "", "")), "parts": []}

    def handle_data(self, data):
        if self.skip_text:
            return
        value = " ".join(data.split())
        if not value:
            return
        self.text.append(value)
        if self.heading is not None:
            self.heading.append(value)
        if self.link is not None:
            self.link["parts"].append(value)
        elif self.last_job is not None and re.match(r"Remote\s*\([^)]+\)", value, re.I):
            locations = self.last_job.setdefault("_locations", [])
            if value not in locations:
                locations.append(value)
                self.last_job["location"] = " / ".join(locations)

    def handle_endtag(self, tag):
        if tag in {"style", "script"} and self.skip_text:
            self.skip_text -= 1
            return
        if self.skip_text:
            return
        if tag in {"h2", "h3"} and self.heading is not None:
            self.department = " ".join(self.heading)
            self.heading = None
        if tag == "a" and self.link is not None:
            title = " ".join(self.link["parts"])
            if title and title.lower() != "view job" and len(title) <= 180:
                job = {
                    "title": title,
                    "location": "",
                    "department": self.department,
                    "url": self.link["url"],
                    "posted_at": "",
                }
                self.jobs.append(job)
                self.last_job = job
            self.link = None


def fetch_rippling(slug):
    """Use only links on the public Rippling board, never private ATS APIs."""
    html = get_html(f"https://ats.rippling.com/embed/{slug}/jobs")
    parser = _RipplingLinks(slug)
    parser.feed(html)
    jobs = list({job["url"]: job for job in parser.jobs}.values())
    for job in jobs:
        job.pop("_locations", None)
    if not jobs and not re.search(r"\b0 roles?\s+across\b", " ".join(parser.text), re.I):
        raise ValueError(f"Rippling board for {slug} had no readable public job listings")
    return jobs


def fetch_waterly(_slug=None):
    """Only current PDF listings linked in Waterly's live careers index."""
    html = get_html("https://www.waterly.com/careers")
    start = re.search(r"We are hiring for the following", html, re.I)
    if not start:
        raise ValueError("Waterly careers page has no recognizable current-openings section")
    end = re.search(r"Think you (?:might|are)", html[start.end():], re.I)
    section = html[start.end():start.end() + end.start()] if end else html[start.end():]
    jobs = []
    seen = set()
    for attrs, body in re.findall(r"<li\b([^>]*)>(.*?)</li>", section, re.I | re.S):
        if re.search(r"\bhidden\b|aria-hidden\s*=\s*['\"]?true|display\s*:\s*none|visibility\s*:\s*hidden", attrs + body.split(">")[0], re.I):
            continue
        for href, title_html in re.findall(r"<a\b[^>]*href=['\"]([^'\"]+\.pdf)['\"][^>]*>(.*?)</a>", body, re.I | re.S):
            if re.search(r"\bhidden\b|display\s*:\s*none|visibility\s*:\s*hidden", title_html, re.I):
                continue
            url = urljoin("https://www.waterly.com/careers", href)
            if urlparse(url).netloc != "www.waterly.com" or "/s/" not in urlparse(url).path:
                continue
            title = re.sub(r"<[^>]+>", " ", title_html)
            title = " ".join(title.split())
            if title and url not in seen:
                seen.add(url)
                jobs.append({
                    "title": title,
                    "location": "Remote" if re.search(r"full-time remote", html, re.I) else "",
                    "department": "",
                    "url": url,
                    "posted_at": "",
                })
    return jobs


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "workable": fetch_workable,
    "recruitee": fetch_recruitee,
    "breezy": fetch_breezy,
    "gusto": fetch_gusto,
    "bamboohr": fetch_bamboohr,
    "floodbase": fetch_floodbase,
    "rippling": fetch_rippling,
    "waterly": fetch_waterly,
}

# ---------------------------------------------------------------------------
# Careers-page scraping fallback (used when ats is null in companies.json)
# ---------------------------------------------------------------------------

# If a careers page embeds or links an ATS, we detect it and use the clean API.
ATS_URL_PATTERNS = {
    "greenhouse": r"(?:boards|job-boards|boards-api)\.greenhouse\.io/(?:v1/boards/)?([A-Za-z0-9_-]+)",
    "lever":      r"jobs\.lever\.co/([A-Za-z0-9_-]+)",
    "ashby":      r"jobs\.ashbyhq\.com/([A-Za-z0-9_-]+)",
    "workable":   r"apply\.workable\.com/([A-Za-z0-9_-]+)",
    "recruitee":  r"https?://([A-Za-z0-9-]+)\.recruitee\.com",
    "breezy":     r"https?://([A-Za-z0-9-]+)\.breezy\.hr",
    "gusto":      r"jobs\.gusto\.com/boards/([A-Za-z0-9-]+)",
    "bamboohr":   r"https?://([A-Za-z0-9-]+)\.bamboohr\.com",
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
    previous_path = HERE / "jobs.json"
    previous = {}
    if previous_path.exists():
        previous = {
            c["name"]: c.get("jobs", [])
            for c in json.loads(previous_path.read_text()).get("companies", [])
        }
    stale_companies = []
    unverified_companies = []
    failed_companies = []
    unsupported_companies = []
    disabled_companies = []

    for c in config["companies"]:
        entry = {
            "name": c["name"],
            "website": c["website"],
            "careers_url": c.get("careers_url") or c["website"],
            "logo": c.get("logo"),
            "description": c.get("description", ""),
            "jobs": [],
            "source_status": "unverified",
        }
        ats = c.get("ats")
        if ats and ats not in FETCHERS:
            unsupported_companies.append(c["name"])
            entry["jobs"] = previous.get(c["name"], [])
            entry["source_status"] = "unsupported_stale" if entry["jobs"] else "unsupported"
            print(f"  {c['name']:<20} {ats:<12} unsupported source", file=sys.stderr)
        elif ats:
            try:
                entry["jobs"] = FETCHERS[ats](c["slug"])
                entry["source_status"] = "ok"
                print(f"  {c['name']:<20} {ats:<12} {len(entry['jobs'])} jobs")
            except Exception as e:
                errors.append(f"{c['name']} ({ats}/{c['slug']}): {e}")
                failed_companies.append(c["name"])
                print(f"  {c['name']:<20} {ats:<12} ERROR: {e}", file=sys.stderr)
        elif c.get("scrape", True) is False:
            disabled_companies.append(c["name"])
            entry["source_status"] = "disabled"
            print(f"  {c['name']:<20} {'unverified':<12} careers link only")
        else:
            try:
                jobs, how = fetch_scraped(entry["careers_url"], render=render)
                entry["jobs"] = jobs
                if how != "no structured jobs found":
                    entry["source_status"] = "ok"
                print(f"  {c['name']:<20} {'scrape':<12} {len(jobs)} jobs ({how})")
            except Exception as e:
                errors.append(f"{c['name']} (scrape): {e}")
                failed_companies.append(c["name"])
                print(f"  {c['name']:<20} {'scrape':<12} ERROR: {e}", file=sys.stderr)
        if c["name"] in failed_companies:
            entry["jobs"] = previous.get(c["name"], [])
            entry["source_status"] = "error_stale" if entry["jobs"] else "error_no_prior"
            if entry["jobs"]:
                stale_companies.append(c["name"])
        elif entry["source_status"] == "unverified":
            unverified_companies.append(c["name"])
        if entry["source_status"] == "unsupported_stale":
            stale_companies.append(c["name"])
        total += len(entry["jobs"])
        out_companies.append(entry)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_jobs": total,
        "companies": out_companies,
        "fetch_errors": errors,
        "stale_companies": stale_companies,
        "unverified_companies": unverified_companies,
        "failed_companies": failed_companies,
        "unsupported_companies": unsupported_companies,
        "disabled_companies": disabled_companies,
    }
    (HERE / "jobs.json").write_text(json.dumps(output, indent=2))
    print(f"\nWrote jobs.json - {total} jobs across "
          f"{sum(1 for c in out_companies if c['jobs'])} companies.")
    if errors:
        print(f"{len(errors)} fetch errors; prior listings retained for: "
              f"{', '.join(stale_companies)}.", file=sys.stderr)


if __name__ == "__main__":
    main()
