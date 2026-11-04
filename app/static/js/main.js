(() => {
  let toastTimer;
  const toast = (message) => {
    const element = document.querySelector('#toast');
    element.textContent = message;
    element.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { element.hidden = true; }, 4500);
  };

  const preparedCovers = new WeakSet();
  const prepare = (root = document) => {
    root.querySelectorAll('img[data-cover]').forEach((image) => {
      if (preparedCovers.has(image)) return;
      preparedCovers.add(image);
      image.addEventListener('error', () => {
        image.src = '/static/placeholder.svg';
      }, { once: true });
      if (image.complete && image.naturalWidth === 0) image.src = '/static/placeholder.svg';
    });
    root.querySelectorAll('[data-local-time]').forEach((element) => {
      const date = new Date(element.dateTime);
      if (!Number.isNaN(date.getTime())) element.textContent = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short' }).format(date);
    });
  };
  prepare();
  const categories = document.querySelector('.category-disclosure');
  if (categories && window.matchMedia('(max-width: 720px)').matches) categories.open = false;

  let refreshing = false;
  document.addEventListener('click', async (event) => {
    const refresh = event.target.closest('[data-refresh]');
    if (refresh) {
      if (refreshing) return;
      refreshing = true;
      const label = refresh.innerHTML;
      refresh.disabled = true;
      refresh.textContent = 'Fetching the latest courses...';
      try {
        const response = await fetch('/api/catalog/refresh', { method: 'POST', headers: { Accept: 'application/json' } });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || 'Catalog refresh failed.');
        toast('Catalog updated.');
        location.reload();
      } catch (error) { toast(error.message || 'Refresh failed. Please try again.'); }
      finally {
        refreshing = false;
        refresh.disabled = false;
        refresh.innerHTML = label;
      }
      return;
    }

    const save = event.target.closest('[data-save]');
    if (save) {
      save.disabled = true;
      try {
        const response = await fetch(`/api/saved/${save.dataset.save}/toggle`, { method: 'POST', headers: { Accept: 'application/json' } });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || 'The course could not be saved.');
        document.querySelectorAll(`[data-save="${save.dataset.save}"]`).forEach((button) => {
          button.classList.toggle('is-saved', result.saved);
          button.setAttribute('aria-pressed', String(result.saved));
          const label = result.saved ? 'Remove bookmark' : 'Save course';
          button.setAttribute('aria-label', `${label}: ${button.dataset.title}`);
          const text = button.querySelector('[data-save-label]');
          if (text) text.textContent = label;
        });
        toast(result.saved ? 'Course saved in this browser.' : 'Bookmark removed.');
        if (new URLSearchParams(location.search).get('kind') === 'saved' && !result.saved) {
          if (window.htmx) window.htmx.trigger('#filters', 'submit');
          else location.reload();
        }
      } catch (error) { toast(error.message || 'The bookmark could not be updated.'); }
      finally { save.disabled = false; }
    }

    const copy = event.target.closest('[data-copy-coupon]');
    if (copy) {
      const code = document.querySelector('#coupon-code').textContent.trim();
      try {
        if (!navigator.clipboard) throw new Error('clipboard unavailable');
        await navigator.clipboard.writeText(code);
        toast('Coupon copied.');
      } catch {
        const selection = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(document.querySelector('#coupon-code'));
        selection.removeAllRanges();
        selection.addRange(range);
        toast('Automatic copying is unavailable. The code is selected so you can copy it manually.');
      }
    }
  });

  document.addEventListener('htmx:beforeRequest', () => {
    document.querySelector('#results')?.setAttribute('aria-busy', 'true');
    const error = document.querySelector('#request-error');
    if (error) error.hidden = true;
  });
  document.addEventListener('htmx:afterRequest', (event) => {
    document.querySelector('#results')?.setAttribute('aria-busy', 'false');
    if (!event.detail.successful) {
      const error = document.querySelector('#request-error');
      if (error) {
        error.firstChild.textContent = event.detail.xhr?.status === 422
          ? 'Invalid search. Use up to 300 characters and valid filters. '
          : 'Results could not be loaded. ';
        error.hidden = false;
      }
    }
  });
  document.addEventListener('htmx:afterSwap', (event) => prepare(event.detail.elt));

  // Native GET forms remain usable when the CDN is unavailable.
  if (!window.htmx) {
    const form = document.querySelector('#filters');
    let debounce;
    form?.addEventListener('input', (event) => {
      if (event.target.id !== 'q') return;
      clearTimeout(debounce);
      debounce = setTimeout(() => form.requestSubmit(), 300);
    });
    form?.addEventListener('change', (event) => {
      if (event.target.id !== 'q') form.requestSubmit();
    });
  }
})();
