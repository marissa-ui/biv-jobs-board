# Deploying to jobs.burntislandventures.com

Total time: ~20 minutes of work, plus up to an hour of DNS/certificate wait. Everything is free.

The folder is already structured for this: the nightly workflow is in `.github/workflows/update-jobs.yml` and the `CNAME` file tells GitHub Pages your subdomain. (If a stray `update-jobs.yml` remains in the folder root, delete it — the real one is in `.github/workflows/`.)

## 1. Push to GitHub

Create an empty repo named `biv-jobs-board` at https://github.com/new (public — required for free GitHub Pages). Then:

```bash
cd biv-jobs-board
rm -f update-jobs.yml          # remove root duplicate if present
git init
git add -A
git commit -m "BIV portfolio jobs board"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/biv-jobs-board.git
git push -u origin main
```

## 2. Allow the workflow to commit

Repo → Settings → Actions → General → Workflow permissions → select "Read and write permissions" → Save. (Without this, the nightly job refresh can't push the updated jobs.json.)

## 3. Enable GitHub Pages

Repo → Settings → Pages → Source: "Deploy from a branch" → Branch: `main`, folder `/ (root)` → Save.

In a minute or two the board will be live at `https://YOUR_USERNAME.github.io/biv-jobs-board/`. Check it works before moving on.

## 4. Point the subdomain at it (Squarespace)

In Squarespace: Settings → Domains → burntislandventures.com → DNS Settings → Add Record:

- Type: `CNAME`
- Host: `jobs`
- Data: `YOUR_USERNAME.github.io` (note: no `/biv-jobs-board` — just the bare domain)

## 5. Tell GitHub about the subdomain

Repo → Settings → Pages → Custom domain: enter `jobs.burntislandventures.com` → Save. GitHub will verify the DNS record (can take a few minutes to an hour). Once verified, tick "Enforce HTTPS" — the checkbox enables after the certificate is issued, which can take up to an hour.

Done: the board is live at https://jobs.burntislandventures.com and refreshes itself every night at 6:00 UTC.

## 6. Link it from your site

In Squarespace, edit the existing "Jobs Board" navigation item to link to https://jobs.burntislandventures.com.

## Verify the nightly refresh

Repo → Actions tab → "Update jobs" → Run workflow (manual trigger). Watch the log: it prints one line per company showing how many jobs were found and via which method (ATS API, detected ATS, json-ld, or none). This is also where you'll see which companies the scraper can't reach yet.

## Later updates

Edit `companies.json` (e.g. adding a confirmed ATS slug or a new portfolio company), then:

```bash
git add companies.json && git commit -m "Update companies" && git push
```

The site redeploys automatically on every push.

## Troubleshooting

"DNS check unsuccessful" in step 5: wait 30-60 min for propagation, then Save again. Certificate/HTTPS not available: same — just wait and re-check. Workflow fails with permission error: revisit step 2. Board shows old jobs: check the Actions tab for failed runs; you can always trigger a manual run.
