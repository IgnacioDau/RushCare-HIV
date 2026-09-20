/* ---------- núcleo ---------- */
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const norm = s => String(s).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim();
const rad = d => d * Math.PI / 180;
function km(a, b, c, d) {
  const dl = rad(c - a), dg = rad(d - b);
  const x = Math.sin(dl / 2) ** 2 + Math.cos(rad(a)) * Math.cos(rad(c)) * Math.sin(dg / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(x));
}
const fmtKm = v => v < 1 ? 'menos de 1 km' : (v < 10 ? v.toFixed(1).replace('.', ',') : Math.round(v)) + ' km';
const RADIUS = 50;
const VIGENCIA = 'https://serviciosdigitales.imss.gob.mx/gestionAsegurados-web-externo/vigencia';
const WA_NUM = '525554978251';
const state = { user: null, imss: 'no', types: new Set(['CAPASITS', 'SAIH']), limit: 8, selected: null, fitAll: false };
const TYPE_NAME = { CAPASITS: 'CAPASITS', SAIH: 'Hospital SAIH', IMSS: 'Hospital IMSS' };
const hasRefine = () => typeof Geo !== 'undefined' && !!Geo.refine;

const PLACE_INDEX = [
  ...DATA.places.map(p => ({ label: p[0] + ', ' + p[1], key: norm(p[0]), lat: p[2], lng: p[3] })),
  ...DATA.states.map(s => ({ label: s[0] + ' (estado)', key: norm(s[0]), lat: s[1], lng: s[2] }))
];
function offlineGeocode(q) {
  const n = norm(q); if (!n) return null;
  const cands = PLACE_INDEX.filter(p => p.key === n || n.includes(p.key) || p.key.includes(n));
  cands.sort((a, b) => (a.key === n ? -1 : 0) - (b.key === n ? -1 : 0) || a.key.length - b.key.length);
  return cands[0] ? { lat: cands[0].lat, lng: cands[0].lng, label: cands[0].label.replace(' (estado)', ''), precise: false } : null;
}
function setStatus(html, err) { const s = $('#status'); s.innerHTML = html; s.className = 'status' + (err ? ' err' : ''); }

function activeUnits() {
  return DATA.units.filter(u => state.imss === 'si' ? u.t === 'IMSS' : (u.t !== 'IMSS' && state.types.has(u.t)));
}
function ranked() {
  if (!state.user) return { inside: [], all: [] };
  const all = activeUnits().map(u => ({ ...u, d: km(state.user.lat, state.user.lng, u.lat, u.lng) })).sort((a, b) => a.d - b.d);
  const slack = hasRefine() ? 25 : 0;
  return { all, inside: all.filter(u => u.d <= RADIUS + (u.exact ? 0 : slack)) };
}
function telHref(p) {
  const m = String(p).replace(/\s+/g, ' ').match(/(\d[\d\s-]{8,13}\d)/);
  if (!m) return null;
  const dg = m[1].replace(/\D/g, '');
  return dg.length >= 10 ? 'tel:+52' + dg.slice(0, 10) : null;
}
function dirHref(u) {
  const dest = u.t === 'IMSS' ? u.lat + ',' + u.lng : encodeURIComponent([u.n, u.a, u.l, u.e, 'México'].join(', '));
  const org = state.user && state.user.precise ? '&origin=' + state.user.lat + ',' + state.user.lng : '';
  return 'https://www.google.com/maps/dir/?api=1&destination=' + dest + org;
}
const waHref = () => 'https://wa.me/' + WA_NUM + '?text=' + encodeURIComponent('Hola, quiero agendar una cita de atención VIH');

function docsBlock(u) {
  const L = `<a href="${VIGENCIA}" target="_blank" rel="noopener">Obtenerla aquí</a>`;
  if (u.t === 'CAPASITS') return `<div class="docs"><h4>Documentos</h4>
    <p><b>Necesarios:</b> constancia de no afiliación al IMSS (${L}) e INE o pasaporte.</p>
    <p><b>Recomendado:</b> cartilla de vacunación.</p></div>`;
  if (u.t === 'IMSS') return `<div class="docs"><h4>Documentos</h4>
    <p><b>Necesario:</b> constancia de vigencia de derechos IMSS (${L}).</p>
    <p><b>Recomendados:</b> INE o pasaporte y cartilla de vacunación.</p></div>`;
  return `<div class="docs"><h4>Documentos</h4>
    <p><b>Recomendados:</b> constancia de no afiliación al IMSS (${L}), INE o pasaporte y cartilla de vacunación. Confirma por teléfono qué te piden.</p></div>`;
}
function serviceLine(u) {
  if (u.t === 'CAPASITS') return 'Centro ambulatorio de atención y prevención del VIH/ITS';
  if (u.t === 'IMSS') return u.k + ' · atención de VIH en hospitales de 2.º y 3.er nivel';
  return 'Servicio de atención integral hospitalaria (SAIH)';
}
function card(u, i) {
  const tel = telHref(u.p);
  return `<li class="res${i === 0 ? ' first' : ''}" data-id="${u.id}" ${state.selected === u.id ? 'aria-current="true"' : ''} tabindex="0">
    <div class="pin" aria-hidden="true">${i + 1}</div>
    <div><h3>${esc(u.n)}</h3>
      <div class="meta"><span class="badge">${TYPE_NAME[u.t]}</span><span class="dist">${u.d < 1 ? 'menos de 1 km' : (u.exact ? '' : '≈ ') + fmtKm(u.d)}</span><span>${esc(u.l)}, ${esc(u.e)}</span>${i === 0 ? '<strong style="color:var(--hot)">Más cercano</strong>' : ''}</div></div>
    <div class="det">
      <div><span class="k">Dirección · </span>${esc(u.a)}</div>
      ${u.p ? `<div><span class="k">Teléfono · </span>${tel ? `<a href="${tel}">${esc(u.p)}</a>` : esc(u.p)}</div>` : ''}
      ${u.h ? `<div><span class="k">Horario · </span>${esc(u.h)}</div>` : ''}
      <div><span class="k">Servicio · </span>${esc(serviceLine(u))}</div>
    </div>
    ${docsBlock(u)}
    <div class="acts"><a class="btn small" href="${dirHref(u)}" target="_blank" rel="noopener">Cómo llegar</a>${tel ? `<a class="btn ghost small" href="${tel}">Llamar</a>` : ''}${u.t === 'IMSS' ? `<a class="btn ghost small" href="${waHref()}" target="_blank" rel="noopener">Cita por WhatsApp</a>` : ''}</div>
  </li>`;
}
function chatCard() {
  return `<div class="chat"><h3>Agenda tu cita por WhatsApp</h3>
    <p>Chatbot <b>Atención VIHrtual</b> del IMSS, disponible las 24 horas: agenda citas, da seguimiento a tu atención y resuelve dudas sobre PrEP y PEP.</p>
    <a class="btn" href="${waHref()}" target="_blank" rel="noopener">Abrir WhatsApp · 55 5497 8251</a>
    <small>También puedes escribir a atencion.vih@imss.gob.mx</small></div>`;
}

let refineTimer = 0;
function render() {
  const out = $('#out'), im = state.imss === 'si';
  $('#chips').hidden = im;
  let head = im ? chatCard() : '', body = '', shown = [];
  if (state.user) {
    const { inside, all } = ranked();
    if (!all.length) body = '<p class="status">Activa al menos un tipo de centro.</p>';
    else if (!inside.length) {
      const n = all[0]; shown = [n];
      body = `<p class="note">No hay ${im ? 'hospitales del IMSS' : 'centros'} a menos de ${RADIUS} km de ${esc(state.user.label)}. El más cercano está a ${fmtKm(n.d)}:</p><ul class="results" style="margin-top:8px">${card(n, 0)}</ul>`;
    } else {
      shown = inside.slice(0, state.limit);
      body = `<p class="approx">${inside.length} ${inside.length === 1 ? 'resultado' : 'resultados'} a menos de ${RADIUS} km, del más cercano al más lejano.${im ? ' Los hospitales del IMSS de 2.º y 3.er nivel atienden VIH; confirma por WhatsApp o en tu UMF si tu hospital tiene clínica de VIH.' : ' Las distancias con ≈ se miden hasta el centro del municipio.'}</p>
        <ul class="results" style="margin-top:8px">${shown.map(card).join('')}</ul>
        ${inside.length > shown.length ? '<button class="btn ghost more" id="more" type="button" style="margin-top:12px">Ver más lugares</button>' : ''}`;
    }
    if (!im) scheduleRefine(all.filter(u => u.d <= RADIUS + 25).slice(0, 12));
  }
  out.innerHTML = head + body;
  MapAdapter.update({ user: state.user, shown, context: activeUnits(), selected: state.selected, fitAll: state.fitAll });
  $('#legend').innerHTML = state.user ? '<b style="color:var(--user)">●</b> Tú &nbsp; <b style="color:var(--accent)">●</b> Resultados' : 'Cada punto es una unidad del directorio';
  $('#gmlink').href = state.user
    ? `https://www.google.com/maps/@${state.user.lat},${state.user.lng},13z`
    : 'https://www.google.com/maps/@23.6345,-102.5528,5z';
}
function scheduleRefine(items) {
  if (!hasRefine()) return;
  clearTimeout(refineTimer);
  refineTimer = setTimeout(async () => { if (await Geo.refine(items)) { const f = Geo.refine; Geo.refine = null; render(); Geo.refine = f; } }, 250);
}
async function locate(q) {
  setStatus('Buscando…');
  const g = (typeof Geo !== 'undefined' && Geo.geocode) ? await Geo.geocode(q) : offlineGeocode(q);
  if (!g) { setStatus('No encontré ese lugar. Prueba con el nombre de tu ciudad o estado, o usa tu ubicación.', true); return; }
  setUser(g);
}
function setUser(g) {
  state.user = g; state.limit = 8; state.selected = null; state.fitAll = false;
  setStatus('Ubicación: <b>' + esc(g.label) + '</b>' + (g.precise ? '' : ' (centro de la ciudad)'));
  // The location lives in `state`, not in any form control, so the step has to
  // announce itself or steps.js would never let the flow advance.
  document.dispatchEvent(new CustomEvent('rc:answered',
    { detail: { step: 'donde', value: g.label } }));
  render();
}
function selectUnit(id, scroll) {
  state.selected = id;
  document.querySelectorAll('.res').forEach(el => {
    const on = +el.dataset.id === id;
    if (on) el.setAttribute('aria-current', 'true'); else el.removeAttribute('aria-current');
    if (on && scroll) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  });
  MapAdapter.select(id);
}

$('#places').innerHTML = [...new Set(PLACE_INDEX.map(p => p.label))].sort((a, b) => a.localeCompare(b, 'es')).map(l => `<option value="${esc(l)}">`).join('');
$('#btn-geo').addEventListener('click', () => {
  if (!navigator.geolocation) { setStatus('Tu navegador no permite detectar la ubicación. Escribe tu ciudad.', true); return; }
  setStatus('Detectando tu ubicación…');
  navigator.geolocation.getCurrentPosition(
    p => setUser({ lat: p.coords.latitude, lng: p.coords.longitude, label: 'tu ubicación actual', precise: true }),
    () => setStatus('No pude detectar tu ubicación (revisa el permiso del navegador). Escribe tu ciudad o estado.', true),
    { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 });
});
$('#form-loc').addEventListener('submit', e => { e.preventDefault(); locate($('#q').value); });
document.querySelectorAll('input[name="imss"]').forEach(r => r.addEventListener('change', () => { state.imss = r.value; state.limit = 8; state.selected = null; render(); }));
$('#chips').addEventListener('click', e => {
  const b = e.target.closest('.chip'); if (!b) return;
  const t = b.dataset.t, on = b.getAttribute('aria-pressed') === 'true';
  if (on) state.types.delete(t); else state.types.add(t);
  b.setAttribute('aria-pressed', String(!on)); state.limit = 8; render();
});
$('#out').addEventListener('click', e => {
  if (e.target.id === 'more') { state.limit += 8; render(); return; }
  if (e.target.closest('a')) return;
  const li = e.target.closest('.res'); if (li) selectUnit(+li.dataset.id, false);
});
$('#out').addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.classList.contains('res')) selectUnit(+e.target.dataset.id, false); });
$('#btn-fit').addEventListener('click', () => {
  state.fitAll = !state.fitAll; $('#btn-fit').textContent = state.fitAll ? 'Ajustar a mis resultados' : 'Ver todo México'; render();
});
window.addEventListener('map-select', e => selectUnit(e.detail, true));
MapAdapter.init($('#map'));
render();
