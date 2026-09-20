/* 72-hour clock, shared by both regions.
 *
 * Deliberately calm: a plain line of text, no red, no flashing, no ticking.
 * Panic makes people slower, and slower is the one thing this app cannot
 * afford. The countdown is a fact on the screen, not an alarm.
 *
 * The Mexico module is a directory that also serves people who are not in a
 * 72-hour situation at all, so the clock only appears once someone says when
 * the exposure was.
 */
(function () {
  const WINDOW_HOURS = 72;
  const el = document.getElementById('clock');
  const chips = document.getElementById('when');
  const msg = document.getElementById('when-msg');
  const expired = document.getElementById('expired');
  if (!el || !chips) return;

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
      return `Te quedan aproximadamente ${d} ${d === 1 ? 'día' : 'días'} de la ventana de 72 horas.`;
    }
    if (h >= 2) return `Te quedan aproximadamente ${Math.floor(h)} horas de la ventana de 72 horas.`;
    if (h > 0) return 'Queda menos de 2 horas de la ventana. Acude a Urgencias ahora.';
    return 'Pasaron más de 72 horas desde la exposición.';
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
        ? 'Cuanto antes empieces la PEP, mejor funciona.'
        : 'La PEP ya no sería efectiva, pero abajo tienes qué hacer ahora.';
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
      if (msg) msg.textContent = 'Buscando atención de VIH en general.';
      return;
    }
    exposureHoursAgo = Number(raw);
    startedAt = Date.now();
    paint();
  });

  // A minute is fine. A ticking second counter would be theatre.
  setInterval(paint, 60000);
})();
