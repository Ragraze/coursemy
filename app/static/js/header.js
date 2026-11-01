(() => {
  const header = document.querySelector('.site-header');
  const menu = document.querySelector('.header-mobile-menu');
  if (!header || !menu) return;
  let previousY = Math.max(0, window.scrollY);
  let direction = 0;
  let distance = 0;
  let idleTimer;
  const showHeader = () => header.classList.remove('is-scroll-hidden');
  window.addEventListener('scroll', () => {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(showHeader, 2000);
    const currentY = Math.max(0, Math.min(window.scrollY, document.documentElement.scrollHeight - window.innerHeight));
    const delta = currentY - previousY;
    previousY = currentY;
    if (currentY < 100 || menu.open || header.contains(document.activeElement)) {
      showHeader();
      distance = 0;
      return;
    }
    const nextDirection = Math.sign(delta);
    if (!nextDirection) return;
    if (nextDirection !== direction) distance = 0;
    direction = nextDirection;
    distance += Math.abs(delta);
    if (distance >= 12) header.classList.toggle('is-scroll-hidden', direction > 0);
  }, { passive: true });
  header.addEventListener('focusin', showHeader);
  menu.addEventListener('toggle', () => { if (menu.open) showHeader(); });
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
