(() => {
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  document.querySelectorAll('.landing-hero, .page-hero').forEach((hero) => {
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    if (!context) return;
    canvas.className = 'hero-dot-grid';
    canvas.setAttribute('aria-hidden', 'true');
    hero.prepend(canvas);

    let width = 0;
    let height = 0;
    let visible = false;
    let frame = 0;
    let lastDraw = 0;
    let color;
    const draw = (time = 0) => {
      context.clearRect(0, 0, width, height);
      context.fillStyle = color;
      context.globalAlpha = .2;
      context.beginPath();
      for (let y = 14; y < height; y += 28) {
        for (let x = 14; x < width; x += 28) {
          const wave = (Math.sin(x / 110 + y / 150 - time / 1400) + 1) / 2;
          const radius = .65 + wave ** 3 * 1.05;
          context.moveTo(x + radius, y);
          context.arc(x, y, radius, 0, Math.PI * 2);
        }
      }
      context.fill();
    };
    const animate = (time) => {
      if (time - lastDraw >= 32) {
        draw(time);
        lastDraw = time;
      }
      frame = window.requestAnimationFrame(animate);
    };
    const updateMotion = () => {
      window.cancelAnimationFrame(frame);
      if (visible && !document.hidden && !reducedMotion.matches) {
        frame = window.requestAnimationFrame(animate);
      } else if (reducedMotion.matches) {
        draw();
      }
    };
    const resize = () => {
      const bounds = canvas.getBoundingClientRect();
      width = bounds.width;
      height = bounds.height;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      color = getComputedStyle(hero).getPropertyValue('--accent-ink').trim();
      draw();
    };
    resize();
    new ResizeObserver(resize).observe(hero);
    new MutationObserver(resize).observe(document.documentElement, {
      attributes: true, attributeFilter: ['data-theme'],
    });
    new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      updateMotion();
    }).observe(hero);
    reducedMotion.addEventListener('change', updateMotion);
    document.addEventListener('visibilitychange', updateMotion);
  });
})();
