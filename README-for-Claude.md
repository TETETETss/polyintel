# polyintel (Polymarket smart-money tracker)
Live: https://polyintel.pages.dev (Cloudflare Pages project "polyintel")

Files:
- tpl.html: the whole site design (HTML/CSS/JS). Edit this for visual changes.
- build.py: injects data into tpl.html and writes index.html + pub/index.html.
- data/refresh.py: pulls trader positions from the public Polymarket data-api.
- data/prices.py: pulls current market prices.
- .github/workflows/refresh.yml: GitHub Actions runs refresh -> prices -> build -> deploy every 10 minutes (and mktraders.py about every 6h).

Run: python3 data/refresh.py && python3 data/prices.py && python3 build.py
Deploy: export CLOUDFLARE_API_TOKEN=... CLOUDFLARE_ACCOUNT_ID=...
        npx wrangler pages deploy pub --project-name polyintel
Token is NOT included. Create one in Cloudflare with Account > Cloudflare Pages > Edit.

- mktraders.py: refreshes traders.json (Traders page PnL). Run from repo root: python3 mktraders.py (needs internet access to Polymarket).

## Landing page
- Card 001 opens the dashboard directly (no login). The approval-login idea was tried and removed on request.
- #dashboard links do not skip the landing page: the page always starts on the landing page.

## Automation (IMPORTANT)
- GitHub Actions refreshes data and deploys to Cloudflare Pages every ~10 min (cron */10, GitHub may delay runs by several minutes). Manual run: Actions tab > refresh-and-deploy > Run workflow.
- The box loop (loop.sh/cycle.sh) is retired. Edit via this repo from now on: change tpl.html/build.py etc. and push to main; the next run deploys it.
- The bot commits data/*.json, traders.json, index.html after each run, so `git pull --rebase` before pushing.
- Secrets CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID are set as repo secrets. Never commit tokens.
- Deploys are skipped (old page kept) if the build has fewer than 5 markets.
