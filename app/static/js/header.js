(() => {
  const header = document.querySelector('.site-header');
  const menu = document.querySelector('.header-mobile-menu');
  if (!header || !menu) return;
  let revealTimer;
  window.addEventListener('scroll', () => {
    window.clearTimeout(revealTimer);
    const keepVisible = window.scrollY <= 0 || menu.open || header.matches(':has(:focus-visible)');
    header.classList.toggle('is-hidden', !keepVisible);
    if (!keepVisible) {
      revealTimer = window.setTimeout(() => header.classList.remove('is-hidden'), 700);
    }
  }, { passive: true });
  const summary = menu.querySelector('summary');
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && menu.open) {
      menu.open = false;
      summary.focus();
    }
  });
  document.addEventListener('click', (event) => {
    if (menu.open && !menu.contains(event.target)) menu.open = false;
  });
  window.matchMedia('(min-width: 721px)').addEventListener('change', (event) => {
    if (event.matches) menu.open = false;
  });
})();
