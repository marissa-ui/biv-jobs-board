import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fetch_jobs


class FetchJobsTests(unittest.TestCase):
    def test_floodbase_uses_one_employer_listing(self):
        html = '''
        <a href="https://tally.so/r/Npodkp">
          <span>Product</span><span>Full-time</span>
          <h3>VP of Product</h3><span>New York or Boston</span><span>Hybrid</span>
        </a>
        <a href="https://boards.greenhouse.io/floodbase">Careers</a>
        '''
        with patch.object(fetch_jobs, "get_html", return_value=html):
            jobs = fetch_jobs.fetch_floodbase()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "VP of Product")
        self.assertEqual(jobs[0]["url"], "https://tally.so/r/Npodkp")
        self.assertEqual(jobs[0]["location"], "New York or Boston")

    def test_floodbase_new_title_duplicate_and_contact_link(self):
        html = '''
        <a href="https://tally.so/r/contact"><h3>Contact us</h3></a>
        <a href="https://tally.so/r/newrole?source=site">
          <span>Engineering</span><span>Full-time</span>
          <h3>Senior Data Engineer</h3><span>Boston</span><span>Hybrid</span>
        </a>
        <a href="https://www.tally.so/r/newrole/?source=footer">
          <span>Engineering</span><span>Full-time</span>
          <h3>Senior Data Engineer</h3><span>Boston</span>
        </a>
        '''
        with patch.object(fetch_jobs, "get_html", return_value=html):
            jobs = fetch_jobs.fetch_floodbase()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Senior Data Engineer")
        self.assertEqual(jobs[0]["department"], "Engineering")
        self.assertEqual(jobs[0]["url"], "https://tally.so/r/newrole")

    def test_floodbase_removed_listing_is_empty(self):
        with patch.object(fetch_jobs, "get_html", return_value="<h2>Open Roles</h2><p>No openings</p>"):
            self.assertEqual(fetch_jobs.fetch_floodbase(), [])

    def test_floodbase_malformed_job_card_fails_instead_of_clearing(self):
        html = '<a href="https://tally.so/r/job"><span>Full-time</span></a>'
        with patch.object(fetch_jobs, "get_html", return_value=html):
            with self.assertRaises(ValueError):
                fetch_jobs.fetch_floodbase()

    def test_rippling_public_board_changed_title_and_duplicate(self):
        html = '''
        <p>1 role across all departments in all locations</p>
        <h3>Revenue</h3>
        <a href="/en-US/swiftcomply/jobs/81c4c419-4097-4a0c-a0ed-1e5af5b2756f">
          Senior Customer Success Manager
        </a>
        <p>Remote (Canada)</p><p>Remote (United States)</p>
        <a href="https://ats.rippling.com/en-US/swiftcomply/jobs/81c4c419-4097-4a0c-a0ed-1e5af5b2756f">
          <style>.css-mks80q{color:#fff}</style><button>View job</button>
        </a>
        '''
        with patch.object(fetch_jobs, "get_html", return_value=html):
            jobs = fetch_jobs.fetch_rippling("swiftcomply")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Senior Customer Success Manager")
        self.assertEqual(jobs[0]["department"], "Revenue")
        self.assertEqual(jobs[0]["location"], "Remote (Canada) / Remote (United States)")

    def test_rippling_empty_vs_unreadable(self):
        with patch.object(fetch_jobs, "get_html", return_value="<p>0 roles across all departments</p>"):
            self.assertEqual(fetch_jobs.fetch_rippling("swiftcomply"), [])
        with patch.object(fetch_jobs, "get_html", return_value="<div>Loading...</div>"):
            with self.assertRaises(ValueError):
                fetch_jobs.fetch_rippling("swiftcomply")

    def test_waterly_current_index_excludes_hidden_and_old_pdf(self):
        html = '''
        <p>Good with working full-time remote?</p>
        <p>We are hiring for the following position at this time:</p>
        <ul>
          <li><p><a href="/s/Waterly-Sales_Manager.pdf">Sales Manager(s)</a></p></li>
          <li><p><a href="/s/Waterly-Sales_Manager.pdf">Sales Manager(s)</a></p></li>
          <li style="display:none"><a href="/s/Waterly-Head-of-Product.pdf">Head of Product</a></li>
        </ul>
        <p>Think you might be a good fit?</p>
        <a href="/s/Waterly-Head-of-Product.pdf">Cached old role</a>
        '''
        with patch.object(fetch_jobs, "get_html", return_value=html):
            jobs = fetch_jobs.fetch_waterly()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Sales Manager(s)")
        self.assertEqual(jobs[0]["location"], "Remote")
        self.assertEqual(jobs[0]["url"], "https://www.waterly.com/s/Waterly-Sales_Manager.pdf")

    def test_waterly_removed_listing_vs_unrecognized_index(self):
        with patch.object(fetch_jobs, "get_html", return_value="<p>We are hiring for the following positions:</p><ul></ul><p>Think you might be a good fit?</p>"):
            self.assertEqual(fetch_jobs.fetch_waterly(), [])
        with patch.object(fetch_jobs, "get_html", return_value="<h1>Careers</h1><p>Loading</p>"):
            with self.assertRaises(ValueError):
                fetch_jobs.fetch_waterly()

    def test_failed_fetch_retains_prior_roles_and_reports_error(self):
        old_job = {"title": "Existing", "url": "https://example.org/job"}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "companies.json").write_text(json.dumps({"companies": [{
                "name": "Example", "website": "https://example.org",
                "ats": "ashby", "slug": "example"
            }]}))
            (root / "jobs.json").write_text(json.dumps({"companies": [{
                "name": "Example", "jobs": [old_job]
            }]}))
            with patch.object(fetch_jobs, "HERE", root), \
                 patch.dict(fetch_jobs.FETCHERS, {"ashby": lambda _: (_ for _ in ()).throw(RuntimeError("offline"))}), \
                 patch.object(fetch_jobs.sys, "argv", ["fetch_jobs.py"]):
                fetch_jobs.main()
            data = json.loads((root / "jobs.json").read_text())
        self.assertEqual(data["total_jobs"], 1)
        self.assertEqual(data["companies"][0]["jobs"], [old_job])
        self.assertEqual(data["companies"][0]["source_status"], "error_stale")
        self.assertEqual(data["stale_companies"], ["Example"])
        self.assertIn("offline", data["fetch_errors"][0])

    def test_failed_fetch_is_not_double_counted_and_empty_success_clears(self):
        old_job = {"title": "Old", "url": "https://example.org/old"}
        companies = [
            {"name": "Failed", "website": "https://failed.example", "ats": "ashby", "slug": "failed"},
            {"name": "Cleared", "website": "https://cleared.example", "ats": "ashby", "slug": "cleared"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "companies.json").write_text(json.dumps({"companies": companies}))
            (root / "jobs.json").write_text(json.dumps({"companies": [
                {"name": "Failed", "jobs": [old_job]},
                {"name": "Cleared", "jobs": [old_job]},
            ]}))
            def fetch(slug):
                if slug == "failed":
                    raise RuntimeError("offline")
                return []
            with patch.object(fetch_jobs, "HERE", root), \
                 patch.dict(fetch_jobs.FETCHERS, {"ashby": fetch}), \
                 patch.object(fetch_jobs.sys, "argv", ["fetch_jobs.py"]):
                fetch_jobs.main()
            data = json.loads((root / "jobs.json").read_text())
        self.assertEqual(data["total_jobs"], 1)
        self.assertEqual(data["companies"][0]["jobs"], [old_job])
        self.assertEqual(data["companies"][1]["jobs"], [])
        self.assertEqual(data["companies"][1]["source_status"], "ok")
        self.assertEqual(data["stale_companies"], ["Failed"])

    def test_unverified_disabled_and_unsupported_are_distinct(self):
        companies = [
            {"name": "No markup", "website": "https://none.example", "ats": None},
            {"name": "Disabled", "website": "https://disabled.example", "ats": None, "scrape": False},
            {"name": "Unsupported", "website": "https://unsupported.example", "ats": "unknown", "slug": "x"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "companies.json").write_text(json.dumps({"companies": companies}))
            with patch.object(fetch_jobs, "HERE", root), \
                 patch.object(fetch_jobs, "fetch_scraped", return_value=([], "no structured jobs found")), \
                 patch.object(fetch_jobs.sys, "argv", ["fetch_jobs.py"]):
                fetch_jobs.main()
            data = json.loads((root / "jobs.json").read_text())
        self.assertEqual([c["source_status"] for c in data["companies"]],
                         ["unverified", "disabled", "unsupported"])
        self.assertEqual(data["unverified_companies"], ["No markup"])
        self.assertEqual(data["disabled_companies"], ["Disabled"])
        self.assertEqual(data["unsupported_companies"], ["Unsupported"])

    def test_portfolio_additions_preserve_existing_companies(self):
        config = json.loads((fetch_jobs.HERE / "companies.json").read_text())
        names = {c["name"] for c in config["companies"]}
        prior_names = {
            "2S Water", "Aclarity", "AlgaFilm", "Aqua Membranes",
            "Aquafortus", "Aquatic Labs", "AquiSense", "Beagle Services",
            "Cala Systems", "CivilGrid", "CNSRV", "Daupler", "Flocean",
            "Floodbase", "HOPE Hydration", "Irrigreen", "Laiier",
            "NLine Energy", "Power & Water", "Previsico", "SewerAI",
            "Showerstream", "Spout", "Subeca", "SwiftComply", "TeamSolve",
            "Waterly", "Ziptility", "ZwitterCo",
        }
        self.assertEqual(len(prior_names), 29)
        self.assertEqual(len(names), 34)
        self.assertEqual(names - prior_names,
                         {"Biota", "CREW Carbon", "Current Software", "EPOCH", "Verdi"})
        self.assertFalse(prior_names - names)

    def test_verified_careers_links_and_source_configs(self):
        config = json.loads((fetch_jobs.HERE / "companies.json").read_text())
        by_name = {c["name"]: c for c in config["companies"]}
        expected_urls = {
            "2S Water": "https://www.2swater.com/work-with-us/",
            "Laiier": "https://www.laiier.io/careers",
            "Subeca": "https://www.subeca.com/careers",
            "Cala Systems": "https://www.calasystems.com/mission-and-careers",
            "Flocean": "https://www.flocean.green/jobs",
            "Power & Water": "https://www.powerandwater.com/jobs.php",
            "Previsico": "https://previsico.com/careers",
            "Spout": "https://www.spoutwater.com/pages/contact",
            "Waterly": "https://www.waterly.com/careers",
            "SwiftComply": "https://www.swiftcomply.com/careers/",
        }
        for name, url in expected_urls.items():
            self.assertEqual(by_name[name]["careers_url"], url)
        self.assertEqual((by_name["SwiftComply"]["ats"], by_name["SwiftComply"]["slug"]),
                         ("rippling", "swiftcomply"))
        self.assertEqual(by_name["Waterly"]["ats"], "waterly")
        self.assertIsNone(by_name["AlgaFilm"]["ats"])


if __name__ == "__main__":
    unittest.main()
