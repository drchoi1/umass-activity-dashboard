(function () {
  const build = document.querySelector('meta[name="dashboard-build"]')?.content;
  let checking = false;

  async function checkFreshness() {
    if (!build || checking || document.visibilityState === 'hidden') return;
    checking = true;
    try {
      const probe = new URL(window.location.href);
      probe.searchParams.set('_fresh', Date.now());
      const response = await fetch(probe, { cache: 'no-store' });
      if (!response.ok) return;
      const source = await response.text();
      const match = source.match(/<meta name="dashboard-build" content="([^"]+)"/);
      if (match && match[1] !== build) {
        const next = new URL(window.location.href);
        next.searchParams.delete('_fresh');
        next.searchParams.set('v', match[1]);
        window.location.replace(next.href);
      }
    } catch (_) {
      // Stay usable offline and try again the next time the shortcut is shown.
    } finally {
      checking = false;
    }
  }

  window.addEventListener('pageshow', checkFreshness);
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) checkFreshness();
  });
  window.setInterval(checkFreshness, 300000);
})();
