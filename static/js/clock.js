/* 72-hour clock, shared by both regions.
 *
 * Deliberately calm: a plain line of text, no red, no flashing, no ticking.
 * Panic makes people slower, and slower is the one thing this app cannot
 * afford. The countdown is a fact on the screen, not an alarm.
 *
 * The Mexico module is a directory that also serves people who are not in a
 * 72-hour situation at all, so the clock only appears once someone says when
 * the exposure was.
 *
 * All copy comes from window.STRINGS.clock (set by boston.html / mexico.html
 * from strings/<region>/<lang>.json) so this file never hardcodes a language
 * — a region viewed in English must never show a Spanish sentence here.
 */
(function () {
  const WINDOW_HOURS = 72;
  const el = document.getElementById('clock');
  const chips = document.getElementById('when');
  const msg = document.getElementById('when-msg');
  const expired = document.getElementById('expired');
  if (!el || !chips) return;

  const C = (window.STRINGS && window.STRINGS.clock) || {};
  const t = (key, fallback) => C[key] || fallback;

  let exposureHoursAgo = null;
  let startedAt = null;

  function hoursLeft() {
    if (exposureHoursAgo === null) return null;
    const elapsed = (Date.now() - startedAt) / 3600000;
    return WINDOW_HOURS - exposureHoursAgo - elapsed;
  }

  function label(h) {
    if (h >= 24) {
      const d = Math.floor(h / 24);
      const key = d === 1 ? 'days_left_one' : 'days_left_other';
      const fb = d === 1
        ? 'About 1 day left in the 72-hour window.'
        : `About ${d} days left in the 72-hour window.`;
      return t(key, fb).replace('{n}', d);
    }
    if (h >= 2) return t('hours_left', 'About {n} hours left in the 72-hour window.').replace('{n}', Math.floor(h));
    if (h > 0) return t('urgent', 'Less than 2 hours left in the window. Go to an emergency room now.');
    return t('expired', 'More than 72 hours have passed since the exposure.');
  }

  function paint() {
    const h = hoursLeft();
    if (h === null) { el.hidden = true; return; }
    el.hidden = false;
    el.textContent = label(h);
    el.classList.toggle('urgent', h > 0 && h < 6);
    if (expired) expired.hidden = h > 0;
    if (msg) {
      msg.textContent = h > 0
        ? t('reminder_active', 'The sooner you start PEP, the better it works.')
        : t('reminder_expired', 'PEP would no longer be effective, but there is still something you can do below.');
    }
  }

  chips.addEventListener('click', function (e) {
    const b = e.target.closest('.chip');
    if (!b) return;
    chips.querySelectorAll('.chip').forEach(c => c.setAttribute('aria-pressed', 'false'));
    b.setAttribute('aria-pressed', 'true');
    const raw = b.dataset.h;
    if (raw === '') {                 // "not about an exposure"
      exposureHoursAgo = null;
      el.hidden = true;
      if (expired) expired.hidden = true;
      if (msg) msg.textContent = t('not_exposure', '');
      return;
    }
    exposureHoursAgo = Number(raw);
    startedAt = Date.now();
    paint();
  });

  // A minute is fine. A ticking second counter would be theatre.
  setInterval(paint, 60000);
})();
