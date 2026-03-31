# COT Viewer — Auto-Updating CFTC Non-Commercial Positioning

A self-contained HTML viewer for CFTC Commitment of Traders data (Legacy Futures-Only, Non-Commercial positions), auto-updated weekly via GitHub Actions and hosted free on GitHub Pages.

## What It Shows

- **429 futures contracts** across Metals, Energy, Agriculture, Currencies, Equity Indices, Bonds & Rates, Crypto, and more
- **52 weeks** of rolling weekly data
- **Per-week columns**: Net Position, WoW Δ Net, WoW Δ Long, WoW Δ Short
- **Price overlay** for ~54 major contracts (via yfinance)
- **Interactive chart** (dual-axis: net position + price) and **sortable table**
- **Category filter**, **search**, and **prev/next navigation** (arrow keys work too)

## Setup (One-Time, ~5 Minutes)

### Step 1: Create a GitHub repo

1. Go to [github.com/new](https://github.com/new)
2. Name it `cot-viewer` (or whatever you like)
3. Set it to **Public** (required for free GitHub Pages)
4. **Do NOT** initialize with README (we'll push our own files)
5. Click **Create repository**

### Step 2: Push this code

```bash
cd cot-viewer
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/cot-viewer.git
git push -u origin main
```

### Step 3: Enable GitHub Pages

1. Go to your repo → **Settings** → **Pages** (left sidebar)
2. Source: **Deploy from a branch**
3. Branch: `main`, folder: `/docs`
4. Click **Save**

### Step 4: Run the first update

1. Go to your repo → **Actions** tab
2. Click **Update COT Viewer** on the left
3. Click **Run workflow** → **Run workflow**
4. Wait ~1 minute for it to complete

### Step 5: View your site

Your COT viewer is now live at:
```
https://YOUR_USERNAME.github.io/cot-viewer/
```

## How It Works

- **Every Saturday at 06:00 UTC** (11:30 AM IST), a GitHub Action:
  1. Downloads the latest CFTC Legacy COT zip files (current year + previous year)
  2. Processes Non-Commercial Long/Short positions and WoW changes
  3. Fetches price data for ~54 major contracts via yfinance
  4. Generates a single self-contained `index.html` with all data embedded
  5. Commits and pushes to `docs/`, which GitHub Pages serves automatically

- **CFTC publishes** every Friday ~3:30 PM ET, so Saturday morning is the ideal refresh window
- **No server, no database, no API keys** — everything runs in GitHub's free CI/CD

## Manual Refresh

Trigger anytime from the Actions tab → **Run workflow**. Useful if CFTC publishes late or you want an off-cycle update.

## Local Development

```bash
pip install pandas yfinance
python update_cot.py                    # generates cot_viewer.html in current dir
python update_cot.py -o docs -f index.html  # same as GitHub Actions does
```

## Customization

- **Add more price tickers**: Edit the `TICKER_MAP` dict in `update_cot.py`
- **Change lookback**: Edit `LOOKBACK_WEEKS` (default: 52)
- **Change schedule**: Edit the cron in `.github/workflows/update_cot.yml`
- **Add new categories**: Edit the `categorize()` function
