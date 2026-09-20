/* Progressive disclosure for the intake questions, shared by both regions.
 *
 * Only the next unanswered question is shown at full size. Answered ones
 * collapse to a one-line summary you can click to reopen; questions still to
 * come stay visible as dim headings, so the person can see the form is short.
 *
 * This module deliberately owns no state of its own. It listens on `document`,
 * which means it always runs after the region modules and clock.js have
 * already written `aria-pressed` / `checked` on the control that was clicked,
 * and then reads the answer back out of the DOM. Script order does not matter
 * and there is no second copy of the answers to drift.
 *
 * Each step declares how to tell whether it has been answered:
 *
 *   <section class="step" data-step="when" data-summary="When"
 *            data-answered-by="#when .chip[aria-pressed='true']">
 *     <h2 tabindex="-1">…</h2>
 *     <div class="step-body"> …controls… </div>
 *     <p class="status">…</p>      <- outside the body, survives collapse
 *   </section>
 *
 * Answers with no DOM trace (dropping a map pin, geolocating) announce
 * themselves instead:
 *
 *   document.dispatchEvent(new CustomEvent('rc:answered',
 *     { detail: { step: 'where', value: 'Pin on the map' } }));
 */
(function () {
  const steps = [...document.querySelectorAll('.step[data-step]')];
  if (!steps.length) return;

  const forced = new Map();   // step name -> summary text, for answers the DOM cannot show
  let opened = null;          // step reopened via "Change"; outranks the natural frontier
  let first = true;

  const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

  const isAnswered = s =>
    forced.has(s.dataset.step) ||
    !!(s.dataset.answeredBy && document.querySelector(s.dataset.answeredBy));

  /* Live DOM wins over a remembered value: someone who drops a pin and then
     picks a neighbourhood should see the neighbourhood. */
  function summaryValue(s) {
    const body = s.querySelector('.step-body') || s;

    const sel = body.querySelector('select');
    if (sel && sel.value) return sel.options[sel.selectedIndex].textContent.trim();

    const radio = body.querySelector('input[type="radio"]:checked');
    if (radio) {
      const label = body.querySelector(`label[for="${radio.id}"]`);
      const strong = label && label.querySelector('strong');
      return (strong || label || radio).textContent.trim();
    }

    const chip = body.querySelector('.chips:not(.inline) .chip[aria-pressed="true"]');
    if (chip) return chip.dataset.short || chip.textContent.trim();

    return forced.get(s.dataset.step) || '';
  }

  function paintSummary(s) {
    let row = s.querySelector('.step-summary');
    if (!row) {
      row = document.createElement('button');
      row.type = 'button';
      row.className = 'step-summary';
      s.prepend(row);
    }
    row.innerHTML =
      `<span class="k"></span><span class="v"></span><span class="chg"></span>`;
    row.querySelector('.k').textContent = s.dataset.summary || '';
    row.querySelector('.v').textContent = summaryValue(s);
    row.querySelector('.chg').textContent = s.dataset.change || 'Change';
    row.setAttribute('aria-label',
      `${s.dataset.summary || ''}: ${summaryValue(s)}. ${s.dataset.change || 'Change'}`);
  }

  function reveal(el) {
    if (first || !el.offsetParent) return;
    el.scrollIntoView({ block: 'nearest', behavior: reduced() ? 'auto' : 'smooth' });
  }

  function recompute(advance) {
    const frontier = steps.findIndex(s => !isAnswered(s));
    const cur = opened || (frontier < 0 ? null : steps[frontier]);

    steps.forEach((s, i) => {
      const state = s === cur ? 'current'
        : isAnswered(s) ? 'done'
        : (frontier >= 0 && i > frontier) ? 'upcoming'
        : 'current';
      s.dataset.state = state;
      if (state === 'done') paintSummary(s);
      else s.querySelector('.step-summary')?.remove();
    });

    if (advance && cur && cur.offsetParent) {
      // The control that was just clicked is about to be display:none'd, which
      // would drop focus to <body> and throw a screen reader back to the top.
      cur.querySelector('h2')?.focus();
      reveal(cur);
    }
    first = false;
  }

  document.addEventListener('click', e => {
    const summary = e.target.closest('.step-summary');
    if (summary) {
      opened = summary.closest('.step');
      recompute(false);
      opened.querySelector('.step-body')
        ?.querySelector('button,input,select,a[href]')?.focus();
      return;
    }
    // Optional modifiers and result filters are not questions and never gate.
    if (e.target.closest('[data-optional]')) return;
    if (e.target.closest('.chip')) { opened = null; recompute(true); }
  });

  document.addEventListener('change', e => {
    if (e.target.matches('input[name="cov"],input[name="imss"],#hood')) {
      opened = null;
      recompute(true);
    }
  });

  document.addEventListener('rc:answered', e => {
    const d = e.detail;
    const name = typeof d === 'string' ? d : d.step;
    forced.set(name, typeof d === 'string' ? '' : (d.value || ''));
    opened = null;
    recompute(true);
  });

  recompute(false);
})();
