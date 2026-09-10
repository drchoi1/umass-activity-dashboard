# UMass Daily Activity Dashboard

Mobile-first GitHub Pages dashboard for:

- Mullins Center public skating
- RecWell / RockWell / pool hours
- selected group fitness
- live public spot availability
- RecWell facility alerts

The page updates at about **8 AM and 8 PM Eastern every day**, including weekends and holidays. The group-fitness timetable is re-read on every update; a failed parse keeps the last known-good schedule.

## Deploy

1. Create a GitHub repository, e.g. `umass-activity-dashboard`.
2. Unzip this package and upload **everything** to the repository root, including the hidden `.github` folder.
3. In the repository, go to **Settings → Pages**.
   - Source: **Deploy from a branch**
   - Branch: `main`
   - Folder: `/ (root)`
   - Save.
4. Go to **Settings → Actions → General**.
   - Under **Workflow permissions**, select **Read and write permissions**.
   - Save.
5. Go to **Actions → Update UMass Activity Dashboard → Run workflow**.
6. When it finishes, return to **Settings → Pages**. Your URL will normally look like:
   `https://YOUR-USERNAME.github.io/umass-activity-dashboard/`
7. Bookmark that page on your phone.

No API keys, OAuth, Google account authorization, Google Cloud, or GitHub secrets are needed.

## Refresh rules

### Around 8 AM every day
- public skating
- RecWell hours / facility alert
- today's selected group-fitness availability
- page timestamp

### Around 8 PM every day
Rechecks the dynamic sources and availability and rewrites the page.

GitHub's scheduler can be a few minutes late. The workflow handles EST/EDT by scheduling both possible UTC hours and only running when New York local time is 8 AM or 8 PM.

## Selected classes

Configured in `config.json`:

- Pilates 60
- Vinyasa Yoga 60
- Slow Flow Yoga 60
- Zumba 60
- Yin Yoga 60

Each class row links directly to that class's public RecWell registration page.

## Files

- `index.html` — the GitHub Pages page; rewritten automatically
- `update_dashboard.py` — scraper + renderer
- `config.json` — sources, class preferences, reservation URLs
- `data/group_schedule.json` — last good weekly fitness schedule
- `data/availability.json` — availability cache
- `data/state.json` — last-run diagnostics, including scraper errors and class count
- `.github/workflows/update.yml` — twice-daily automation

## First-version caveat

Mullins/Finnly and RecWell's reservation pages are JavaScript-rendered. This version uses Playwright/Chromium and conservative text matching. If either public site changes its markup, the page shows `Schedule check unavailable` / `Availability unavailable` instead of guessing. Every section remains linked to the source for manual verification.
