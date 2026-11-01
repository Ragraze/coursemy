(() => {
  const root = document.documentElement;
  const system = window.matchMedia('(prefers-color-scheme: dark)');
  let preference = 'system';
  try {
    const saved = localStorage.getItem('coursemy-theme');
    if (['light', 'dark', 'system'].includes(saved)) preference = saved;
  } catch {}
  const apply = () => {
    root.dataset.theme = preference === 'system' ? (system.matches ? 'dark' : 'light') : preference;
    root.style.colorScheme = root.dataset.theme;
    document.querySelectorAll('[data-theme-choice]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.themeChoice === preference));
    });
  };
  apply();
  system.addEventListener('change', apply);
  document.addEventListener('DOMContentLoaded', apply);
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-theme-choice]');
    if (!button) return;
    preference = button.dataset.themeChoice;
    try { localStorage.setItem('coursemy-theme', preference); } catch {}
    apply();
  });
  window.addEventListener('storage', event => {
    if (event.key !== 'coursemy-theme') return;
    preference = ['light', 'dark', 'system'].includes(event.newValue) ? event.newValue : 'system';
    apply();
  });
})();
