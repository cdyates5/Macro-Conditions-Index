# Financial Conditions Lead Index

A self-contained macro dashboard: a composite of the **US dollar**, **commodity
prices** and **bond yields** — the three legs of the "growth tax" — standardised
and advanced to lead the **ISM Manufacturing PMI** and equity YoY returns. A
reconstruction of the GMI / Alpine Macro style financial-conditions lead indicator.

**Live site:** `https://<your-username>.github.io/<repo-name>/`

---

## Contents

| File | Purpose |
|---|---|
| `index.html` | The whole dashboard — Chart.js and all data inlined. Open it locally, no server needed. |
| `refresh.py` | Re-pulls data, recomputes, rewrites the data blob inside `index.html`. |
| `data/ism.csv` | ISM Manufacturing PMI history (never revised — this is the durable record). |
| `requirements.txt` | `numpy`, `requests`. |
| `.github/workflows/refresh.yml` | Scheduled auto-refresh + commit. |

---

## Deploy in 10 minutes

### 1. Create the repository
Create a **new repository on GitHub** — call it whatever you like (e.g. `fci-lead-index`).
Make it **Public** (GitHub Pages is free for public repos; private needs a paid plan).
Don't add a README — you have one.

### 2. Upload these files
Easiest route, no git required: on the empty repo page click
**uploading an existing file**, drag in everything, and commit.

> ⚠️ The drag-and-drop uploader silently skips dot-folders, so `.github/` usually
> won't make it. After uploading the rest, click **Add file → Create new file**,
> type `.github/workflows/refresh.yml` as the filename (typing the slashes creates
> the folders), paste the workflow contents, and commit.

Using git instead:
```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

### 3. Turn on GitHub Pages
**Settings → Pages →** under *Build and deployment*, set **Source: Deploy from a
branch**, **Branch: `main`**, **Folder: `/ (root)`** → **Save**.
Wait ~1 minute, then load `https://<you>.github.io/<repo>/`. Because the file is
named `index.html` it is served at the root automatically.

### 4. Allow the workflow to commit
**Settings → Actions → General →** scroll to *Workflow permissions* → select
**Read and write permissions** → **Save**. Without this the scheduled job runs but
can't push its result.

### 5. Test it
**Actions** tab → **Refresh dashboard** → **Run workflow**. It should finish green
in under a minute and — if any data moved — push a commit named `Auto-refresh: …`.
Pages redeploys automatically within a minute or so.

---

## How the auto-refresh works

The workflow runs **07:10 UTC, Tue–Sat** (after the prior US session close) and on
demand via **Run workflow**. Each run pulls the market legs, tops up ISM, recomputes
everything, and commits `index.html` only if something actually changed — so an
unchanged day produces no commit and no redeploy.

To change the cadence, edit the `cron` line in the workflow (times are **UTC**):

| Cadence | cron |
|---|---|
| Weekdays 07:10 | `10 7 * * 1-5` |
| Mondays only | `10 7 * * 1` |
| 1st & 15th monthly | `10 7 1,15 * *` |

GitHub may delay scheduled runs at busy times, and **disables schedules on repos
with no activity for 60 days** (a push or a manual run re-arms it).

---

## The ISM design decision

ISM Manufacturing PMI is **never revised**, so its history lives in `data/ism.csv`
rather than being re-scraped in full on every run. Each run appends only the newest
print. This matters because free ISM endpoints are unreliable — during development
one provider started returning corrupted values and another began returning HTTP 403.

Consequences worth knowing:

- If the latest-print source is unavailable, **the run still succeeds** using the
  stored history; the dashboard simply carries the prior ISM vintage.
- The script **validates four never-revised cycle troughs** (Apr 2020 = 41.5,
  Dec 2008 = 32.9, Jan 1991 = 39.2, Oct 2001 = 40.8) before using the file. If those
  drift it aborts rather than publishing bad data.
- Adding a print **by hand** is one line appended to `data/ism.csv`:
  ```
  2026-09,54.1
  ```
  Use the **reference month**, not the release month — the September figure released
  in early October is `2026-09`.

Market legs (DXY, S&P GSCI, UST 10Y, S&P 500, Nasdaq 100) come from Yahoo Finance
daily closes resampled to month-end, and are re-pulled in full each run.

---

## Running locally

```bash
pip install -r requirements.txt
python refresh.py --dry-run     # compute + print the summary, write nothing
python refresh.py               # refresh index.html in place
```

Then just open `index.html` in a browser.

---

## Method, briefly

Each leg is converted to a stationary **tightness** signal — deviation from its
36-month moving average, z-scored over the full sample — because raw year-on-year
changes are *pro-cyclical* and therefore coincide with ISM rather than lead it.
The composite is `FCI = −mean(z)`, so higher = easier conditions.

`ISM(t) = β₀ + β·tightness(t − lead)` is fitted by OLS at each lead from 6–18
months; the fitted line is the index in PMI points and extending it with the latest
conditions projects ISM forward. All three β's carry the expected negative sign.

**Honest limits.** In this reconstruction the correlation with ISM peaks near a
**15-month** lead (r ≈ 0.52), not the ~9 months GMI cites, and the fit at any lead is
modest (R² ≈ 0.25 at 12m) — financial conditions are one input to the manufacturing
cycle, not the whole of it. The equity relationship is weaker still and
**regime-dependent**: strong over the 2017→ window GMI displays (r ≈ 0.59 for the
Nasdaq 100 at a 6-month lead) but close to nothing pre-2017 (full-sample r ≈ 0.20).
Both figures are shown on the panel. Reconstruction for research — not investment
advice, and not affiliated with GMI or Alpine Macro.
