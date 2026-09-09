# UMass Activity Dashboard v2

New features:
- ‹ / › date navigation across the current Monday–Sunday week.
- Availability refreshes: 8 AM checks today + tomorrow; 8 PM checks tomorrow + the following day. This yields D−2 8 PM, D−1 8 AM, D−1 8 PM, D-day 8 AM.
- First-discovery yellow highlighting for changed skating, hours, fitness schedule, or facility alert information. The highlight disappears on the next unchanged run.
- **Update now** opens the repository's GitHub Actions workflow page. A public GitHub Pages page cannot safely fire `workflow_dispatch` itself without exposing a GitHub credential.

## Upgrade existing repository
Replace the matching files/folders with this package. If your current `data/group_schedule.json` is more complete than the seed here, keep yours.

Then run:
**Actions → Update UMass Activity Dashboard → Run workflow**

Keep **Settings → Actions → General → Workflow permissions → Read and write permissions** enabled.
