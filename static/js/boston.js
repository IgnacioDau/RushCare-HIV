/* Boston flow: four questions, then the router decides.
 *
 * All ranking happens server-side in router.py. This file collects answers,
 * calls /api/boston/route and renders what comes back. It deliberately holds no
 * opinion about which site is best - duplicating that judgement in two
 * languages is how the two copies drift apart.
 */
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const S = window.STRINGS || {};
const state = {
  hoursAgo: null,
  coverage: 'uninsured',
  under18: false,
  affiliation: null,
  origin: null,
  results: [],
  selected: null
};

/* ---------- intake ---------- */

$('#when').addEventListener('click', e => {
  const b = e.target.closest('.chip');
  if (!b) return;
  state.hoursAgo = Number(b.dataset.h);
  $('#flow').hidden = state.hoursAgo >= 72;
  refresh();
});

$('#what').addEventListener('click', e => {
  const b = e.target.closest('.chip');
  if (!b) return;
  $('#what').querySelectorAll('.chip').forEach(c => c.setAttribute('aria-pressed', 'false'));
  b.setAttribute('aria-pressed', 'true');
});

// Referral links: shown, never forced. The person decides whether the other
// path fits better, so both panels leave the main flow untouched underneath.
document.querySelectorAll('[data-ref]').forEach(a => {
  a.addEventListener('click', e => {
    e.preventDefault();
    const panel = $('#ref-' + a.dataset.ref);
    panel.hidden = !panel.hidden;
  });
});

document.querySelectorAll('input[name="cov"]').forEach(r =>
  r.addEventListener('change', () => { state.coverage = r.value; refresh(); }));

$('#extras').addEventListener('click', e => {
  const b = e.target.closest('.chip');
  if (!b) return;
  const on = b.getAttribute('aria-pressed') === 'true';
  const kind = b.dataset.x;

  if (kind === 'minor') {
    state.under18 = !on;
    b.setAttribute('aria-pressed', String(!on));
    $('#minor-note').hidden = on;
  } else {
    // MIT and Harvard are mutually exclusive: a campus health service serves
    // one community, and claiming both would unlock sites for someone neither.
    $('#extras').querySelectorAll('[data-x="mit"],[data-x="harvard"]')
      .forEach(c => c.setAttribute('aria-pressed', 'false'));
    state.affiliation = on ? null : kind;
    b.setAttribute('aria-pressed', String(!on));
  }
  refresh();
});

$('#hood').addEventListener('change', e => {
  if (!e.target.value) return;
  const [lat, lon] = e.target.value.split(',').map(Number);
  state.origin = { lat, lon };
  BostonMap.setUser(lat, lon, true);
  refresh();
});

$('#pin-mode').addEventListener('click', e => {
  e.preventDefault();
  $('#legend').textContent = (S.intake && S.intake.legend_pin_mode) || '';
  document.querySelector('.mapwrap').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
});

/* ---------- routing ---------- */

let inFlight = 0;
async function refresh() {
  if (state.hoursAgo === null || !state.origin || state.hoursAgo >= 72) return;
  const ticket = ++inFlight;
  try {
    const res = await fetch('/api/boston/route', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        hours_ago: state.hoursAgo,
        lat: state.origin.lat,
        lon: state.origin.lon,
        coverage_scheme: state.coverage,
        under_18: state.under18,
        affiliation: state.affiliation
      })
    });
    const data = await res.json();
    if (ticket !== inFlight) return;   // a newer answer already arrived
    render(data);
  } catch (err) {
    const r = S.results || {};
    $('#out').innerHTML = `<p class="notice">${esc(r.server_error || 'Could not reach the server.')}
      ${esc(S.legal ? S.legal.er_fallback : 'When in doubt, go to an emergency room.')}</p>`;
  }
}

/* ---------- rendering ---------- */

function warnings(r) {
  const w = S.warnings || {};
  const out = [];
  if (r.flags.waiting) out.push(['wait', w.sooner_is_better]);
  if (r.flags.hsn) out.push(['cost', w.hsn]);
  if (r.flags.out_of_pocket) out.push(['cost', w.pharmacy_out_of_pocket]);
  if (r.flags.unverified) out.push(['data', w.unverified_long || w.unverified]);
  return out.filter(x => x[1])
    .map(([k, t]) => `<p class="warn ${k}">${esc(t)}</p>`).join('');
}

function costLine(r) {
  const t = S.results || {};
  if (r.cost === 0) return t.cost_free || 'Likely no cost to you';
  return (t.cost_estimate || 'Estimated cost: about ${n}').replace('{n}', Math.round(r.cost));
}

function timeLine(r) {
  const t = S.results || {};
  if (r.waits_for_opening) {
    const h = Math.round((r.opens_in_minutes || 0) / 60);
    const tpl = h === 1
      ? (t.opens_at_one || 'Opens at {time} — in about {n} hour')
      : (t.opens_at_other || 'Opens at {time} — in about {n} hours');
    return esc(tpl.replace('{time}', r.opens_at).replace('{n}', h));
  }
  return esc((t.minutes_wait || "About {n} min until you're seen").replace('{n}', r.minutes));
}

function card(r, i) {
  const t = S.results || {};
  const tel = r.phone ? 'tel:+1' + String(r.phone).replace(/\D/g, '') : null;
  const dir = `https://www.google.com/maps/dir/?api=1&destination=${r.lat},${r.lon}`;
  return `<li class="res${i === 0 ? ' first' : ''}" data-id="${r.id}" tabindex="0">
    <div class="pin" aria-hidden="true">${i + 1}</div>
    <div>
      <h3>${esc(r.name)}</h3>
      <div class="meta">
        ${r.is_fallback ? `<span class="badge">${esc(t.always_open || 'Always open')}</span>` : ''}
        <span class="dist">${timeLine(r)}</span>
        <span>${esc(r.area || '')}</span>
      </div>
    </div>
    <div class="det">
      <div><span class="k">${esc(t.address_label || 'Address · ')}</span>${esc(r.address || '')}</div>
      ${r.phone ? `<div><span class="k">${esc(t.phone_label || 'Phone · ')}</span><a href="${tel}">${esc(r.phone)}</a></div>` : ''}
      <div><span class="k">${esc(t.cost_label || 'Cost · ')}</span>${esc(costLine(r))}</div>
    </div>
    <div class="det">${warnings(r)}</div>
    <div class="acts">
      <a class="btn small" href="${dir}" target="_blank" rel="noopener">${esc(t.directions || 'Directions')}</a>
      ${tel ? `<a class="btn ghost small" href="${tel}">${esc(t.call || 'Call')}</a>` : ''}
      <button class="btn ghost small say" type="button" data-hours="${Math.round(state.hoursAgo)}">${esc(t.what_to_say || 'What to say')}</button>
    </div>
  </li>`;
}

function render(data) {
  const out = $('#out');
  state.results = data.results || [];
  const t = S.results || {};

  if (data.outcome === 'OUT_OF_AREA') {
    out.innerHTML = `<p class="notice">${esc(t.out_of_area || 'We only cover the Boston area right now.')}
      <br>${esc(S.legal ? S.legal.er_fallback : '')}</p>`;
    BostonMap.update([]);
    return;
  }

  if (data.outcome === 'NOTHING_OPEN') {
    const n = data.next_opening;
    const w = S.nothing_open || {};
    out.innerHTML = `<div class="notice">
      <h3>${esc(w.title || 'Nothing is open right now')}</h3>
      <p>${esc(w.lead || '')}</p>
      ${n ? `<p><b>${esc(n.name)}</b> opens at ${esc(n.opens_at)}.</p>` : ''}
      <p>${esc((w.time_left || '').replace('{hours}', Math.round(data.minutes_left / 60)))}</p>
      <p>${esc(w.urgency || '')}</p></div>`;
    BostonMap.update(n ? [n] : []);
    return;
  }

  if (!state.results.length) {
    out.innerHTML = `<p class="notice">${esc(t.no_site || 'No site nearby can see you in time.')}
      ${esc(S.legal ? S.legal.er_fallback : '')}</p>`;
    return;
  }

  const banner = data.uses_demo_data
    ? `<p class="approx">${esc((S.warnings || {}).unverified || '')}</p>` : '';
  out.innerHTML = banner +
    `<ul class="results" style="margin-top:8px">${state.results.map(card).join('')}</ul>`;
  BostonMap.update(state.results);
}

/* ---------- what to say ---------- */

function openSay(hours) {
  const tpl = (S.arrival && S.arrival.script) || '';
  $('#say-script').textContent = tpl.replace('{hours}', hours);
  $('#say').hidden = false;
}
$('#say-close').addEventListener('click', () => { $('#say').hidden = true; });
$('#say-copy').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText($('#say-script').textContent);
    const a = S.arrival || {};
    $('#say-copy').textContent = a.copied || 'Copied';
    setTimeout(() => { $('#say-copy').textContent = a.copy || 'Copy'; }, 1500);
  } catch (e) { /* clipboard blocked; the text is on screen to read aloud anyway */ }
});

$('#out').addEventListener('click', e => {
  const say = e.target.closest('.say');
  if (say) { openSay(say.dataset.hours); return; }
  if (e.target.closest('a')) return;
  const li = e.target.closest('.res');
  if (li) {
    state.selected = +li.dataset.id;
    document.querySelectorAll('.res').forEach(el =>
      el.toggleAttribute('aria-current', +el.dataset.id === state.selected));
  }
});

window.addEventListener('map-select', e => {
  const li = document.querySelector(`.res[data-id="${e.detail}"]`);
  if (li) li.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
});

/* ---------- boot ---------- */

BostonMap.init($('#map'), (lat, lon) => {
  state.origin = { lat, lon };
  $('#hood').value = '';
  $('#legend').textContent = (S.intake && S.intake.legend_pin_dropped) || '';
  // Clearing #hood leaves the location step with no DOM trace of an answer,
  // so it has to say so itself or steps.js would never let the flow advance.
  document.dispatchEvent(new CustomEvent('rc:answered',
    { detail: { step: 'where', value: (S.intake && S.intake.pin_answer_summary) || '' } }));
  refresh();
});
