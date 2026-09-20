/* ---------- Google Maps ---------- */
/* Pega aquí tu clave de API de Google Maps (Maps JavaScript API + Geocoding API), o déjala vacía y la página te la pedirá. */
const GOOGLE_MAPS_API_KEY = '';

let gmap, gGeocoder, gMarkers = [], gUser = null, gCtx = [], gReady = null;
const gCache = {};
function loadGoogle(key) {
  if (gReady) return gReady;
  gReady = new Promise((res, rej) => {
    window.__gmInit = () => res();
    window.gm_authFailure = () => { document.getElementById('keybox').hidden = false; document.getElementById('keyerr').textContent = 'Google rechazó la clave. Revisa que tenga habilitadas Maps JavaScript API y Geocoding API.'; };
    const s = document.createElement('script');
    s.src = 'https://maps.googleapis.com/maps/api/js?key=' + encodeURIComponent(key) + '&callback=__gmInit&language=es&region=MX&loading=async';
    s.onerror = () => rej(new Error('No se pudo cargar Google Maps'));
    document.head.appendChild(s);
  });
  return gReady;
}

const GoogleImpl = (() => {
  let pending = null, el;
  const colors = () => { const g = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim(); return { acc: g('--accent'), hot: g('--hot'), ink: g('--accent-ink'), dot: g('--dot'), surf: g('--surface') }; };
  function paint(s) {
    if (!gmap) { pending = s; return; }
    const c = colors();
    gMarkers.forEach(m => m.setMap(null)); gMarkers = [];
    const b = new google.maps.LatLngBounds();
    const all = s.fitAll || !s.shown.length;
    (s.context || []).forEach(u => {
      const m = new google.maps.Marker({ map: gmap, position: { lat: u.lat, lng: u.lng }, clickable: false, icon: { path: google.maps.SymbolPath.CIRCLE, scale: 3.5, fillColor: c.dot, fillOpacity: .8, strokeWeight: 0 } });
      gMarkers.push(m); if (all) b.extend(m.getPosition());
    });
    if (s.user) {
      const m = new google.maps.Marker({ map: gmap, position: { lat: s.user.lat, lng: s.user.lng }, title: 'Tú', zIndex: 999, icon: { path: google.maps.SymbolPath.CIRCLE, scale: 8, fillColor: c.hot, fillOpacity: 1, strokeColor: '#fff', strokeWeight: 3 } });
      gMarkers.push(m); if (!all) b.extend(m.getPosition());
    }
    s.shown.forEach((u, i) => {
      const m = new google.maps.Marker({ map: gmap, position: { lat: u.lat, lng: u.lng }, title: u.n, zIndex: 500 - i,
        label: { text: String(i + 1), color: i === 0 ? '#fff' : c.ink, fontWeight: '700', fontSize: '12px' },
        icon: { path: google.maps.SymbolPath.CIRCLE, scale: u.id === s.selected ? 15 : 12, fillColor: i === 0 ? c.hot : c.acc, fillOpacity: 1, strokeColor: c.surf, strokeWeight: 2 } });
      m.addListener('click', () => window.dispatchEvent(new CustomEvent('map-select', { detail: u.id })));
      gMarkers.push(m); if (!all) b.extend(m.getPosition());
    });
    if (!b.isEmpty()) { gmap.fitBounds(b, 56); google.maps.event.addListenerOnce(gmap, 'idle', () => { if (gmap.getZoom() > 13) gmap.setZoom(13); }); }
  }
  let lastS = null;
  return {
    async init(container, key) {
      el = container;
      try { await loadGoogle(key); } catch (e) { document.getElementById('keyerr').textContent = e.message; throw e; }
      gmap = new google.maps.Map(el, { center: { lat: 23.6, lng: -102.5 }, zoom: 5, mapTypeControl: false, streetViewControl: false, fullscreenControl: false, clickableIcons: false, styles: gDark() ? G_DARK : G_LIGHT });
      gGeocoder = new google.maps.Geocoder();
      window.__gm_ok = true;
      paint(pending || lastS || { shown: [], context: activeUnits() });
      new MutationObserver(() => { gmap.setOptions({ styles: gDark() ? G_DARK : G_LIGHT }); lastS && paint(lastS); }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    },
    update(s) { lastS = s; paint(s); },
    select(id) { if (lastS) { lastS.selected = id; paint(lastS); } }
  };
})();

const GoogleGeo = {
  async geocode(q) {
    const off = offlineGeocode(q);
    if (!gGeocoder) return off;
    return new Promise(res => {
      gGeocoder.geocode({ address: q + ', México', region: 'MX', componentRestrictions: { country: 'MX' } }, (r, st) => {
        if (st === 'OK' && r[0]) {
          const l = r[0].geometry.location;
          res({ lat: l.lat(), lng: l.lng(), label: r[0].formatted_address.replace(', México', ''), precise: true });
        } else res(off);
      });
    });
  },
  /* Afina la posición de los resultados visibles geocodificando su dirección exacta */
  async refine(items) {
    if (!gGeocoder) return false;
    let changed = false;
    for (const u of items.slice(0, 10)) {
      const orig = DATA.units.find(x => x.id === u.id);
      if (orig.exact) continue;
      if (gCache[u.id] === undefined) {
        const q = [u.n, u.a.replace(/\bC\.?P\.?\s*\d{5}/i, ''), u.l, u.e, 'México'].join(', ');
        gCache[u.id] = await new Promise(res => gGeocoder.geocode({ address: q, componentRestrictions: { country: 'MX' } }, (r, st) => {
          if (st === 'OK' && r[0]) { const l = r[0].geometry.location; res({ lat: l.lat(), lng: l.lng() }); } else res(null);
        }));
      }
      const g = gCache[u.id];
      if (g && km(g.lat, g.lng, orig.lat, orig.lng) < 60) { orig.lat = g.lat; orig.lng = g.lng; orig.exact = true; changed = true; }
      else orig.exact = false;
    }
    return changed;
  }
};

/* ---------- selector de mapa: Google (con clave) o Leaflet (sin clave) ---------- */
let MODE = 'leaflet', IMPL = null, pendingS = null;
const MapAdapter = {
  async init(el) {
    const key = GOOGLE_MAPS_API_KEY || (() => { try { return localStorage.getItem('gmkey') || ''; } catch (e) { return ''; } })();
    const box = document.getElementById('keybox'), kb = document.getElementById('btn-gkey');
    document.getElementById('keyform').addEventListener('submit', e => {
      e.preventDefault(); const k = document.getElementById('keyin').value.trim(); if (!k) return;
      try { localStorage.setItem('gmkey', k); } catch (er) {} location.reload();
    });
    document.getElementById('keycancel').addEventListener('click', () => { box.hidden = true; });
    kb.hidden = false;
    kb.addEventListener('click', () => { box.hidden = false; document.getElementById('keyin').focus(); });
    if (key) { try { MODE = 'google'; IMPL = GoogleImpl; await GoogleImpl.init(el, key); kb.textContent = 'Cambiar clave de Google'; } catch (e) { MODE = 'leaflet'; IMPL = null; } }
    if (!IMPL) { MODE = 'leaflet'; IMPL = LeafletImpl; try { await LeafletImpl.init(el); } catch (e) { setStatus(esc(e.message), true); return; } }
    if (pendingS) IMPL.update(pendingS);
  },
  update(s) { pendingS = s; if (IMPL) IMPL.update(s); },
  select(id) { if (IMPL) IMPL.select(id); }
};
const Geo = {
  geocode: q => MODE === 'google' ? GoogleGeo.geocode(q) : LeafletGeo.geocode(q),
  refine: items => MODE === 'google' ? GoogleGeo.refine(items) : LeafletGeo.refine(items)
};
/* ---------- Mapa de calles con Leaflet + OpenStreetMap/CARTO (sin clave) ---------- */
const LeafletImpl = (() => {
  let map, layer, tiles, markers = new Map(), lastS = null, ready = null;
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const isDark = () => { const t = document.documentElement.getAttribute('data-theme'); return t ? t === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches; };
  function load() {
    if (ready) return ready;
    ready = new Promise((res, rej) => {
      const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css'; document.head.appendChild(l);
      const s = document.createElement('script'); s.src = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js'; s.onload = res; s.onerror = () => rej(new Error('No se pudo cargar el mapa. Revisa tu conexión.')); document.head.appendChild(s);
    });
    return ready;
  }
  function setTiles() {
    if (tiles) map.removeLayer(tiles);
    const dark = isDark();
    tiles = L.tileLayer('https://{s}.basemaps.cartocdn.com/' + (dark ? 'dark_all' : 'light_all') + '/{z}/{x}/{y}{r}.png', { maxZoom: 19, subdomains: 'abcd', attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · © <a href="https://carto.com/attributions">CARTO</a>' }).addTo(map);
    document.getElementById('map').classList.toggle('tint', !dark);
  }
  function pinIcon(n, cls) { return L.divIcon({ className: 'lpin-wrap', html: `<div class="lpin ${cls}">${n}</div>`, iconSize: [32, 32], iconAnchor: [16, 16] }); }
  function paint(s) {
    if (!map) { lastS = s; return; }
    lastS = s; layer.clearLayers(); markers.clear();
    const dot = css('--dot');
    (s.context || []).forEach(u => L.circleMarker([u.lat, u.lng], { radius: 4, weight: 1, color: '#fff', fillColor: dot, fillOpacity: .85, interactive: false }).addTo(layer));
    const pts = [];
    if (s.user) { L.marker([s.user.lat, s.user.lng], { icon: L.divIcon({ className: 'lpin-wrap', html: '<div class="luser"></div>', iconSize: [22, 22], iconAnchor: [11, 11] }), zIndexOffset: 1000, keyboard: false }).bindTooltip('Tú').addTo(layer); pts.push([s.user.lat, s.user.lng]); }
    s.shown.forEach((u, i) => {
      const cls = (i === 0 ? 'first ' : '') + (u.id === s.selected ? 'sel ' : '') + (u.exact ? '' : 'approx');
      const m = L.marker([u.lat, u.lng], { icon: pinIcon(i + 1, cls), zIndexOffset: 500 - i, title: u.n, keyboard: false })
        .bindTooltip(u.n + (u.exact ? '' : ' (ubicación aproximada)'), { direction: 'top', offset: [0, -14] }).addTo(layer);
      m.on('click', () => window.dispatchEvent(new CustomEvent('map-select', { detail: u.id })));
      markers.set(u.id, m); pts.push([u.lat, u.lng]);
    });
    if (s.fitAll || !s.shown.length) map.fitBounds([[14.3, -118.4], [32.9, -86.5]], { padding: [10, 10] });
    else map.fitBounds(pts, { padding: [60, 60], maxZoom: 15 });
  }
  return {
    async init(el) {
      await load();
      map = L.map(el, { zoomControl: true, worldCopyJump: false, minZoom: 4 }).setView([23.6, -102.5], 5);
      layer = L.layerGroup().addTo(map); setTiles();
      matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { setTiles(); paint(lastS); });
      new MutationObserver(() => { setTiles(); paint(lastS); }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
      new ResizeObserver(() => map.invalidateSize()).observe(el);
      paint(lastS || { shown: [], context: activeUnits() });
    },
    update: paint,
    select(id) { if (!lastS) return; lastS.selected = id; const m = markers.get(id); const ll = m && m.getLatLng(); paint(lastS); if (ll) map.panTo(ll, { animate: true }); }
  };
})();

/* Búsqueda de direcciones / colonias y afinado de ubicaciones con Nominatim (OpenStreetMap) */
const LeafletGeo = (() => {
  const cache = {};
  let last = 0;
  async function nom(q) {
    const wait = Math.max(0, 1100 - (Date.now() - last)); if (wait) await new Promise(r => setTimeout(r, wait)); last = Date.now();
    try {
      const r = await fetch('https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&countrycodes=mx&accept-language=es&q=' + encodeURIComponent(q));
      const j = await r.json(); return j[0] ? { lat: +j[0].lat, lng: +j[0].lon, name: j[0].display_name } : null;
    } catch (e) { return null; }
  }
  return {
    async geocode(q) {
      const off = offlineGeocode(q);
      const g = await nom(q);
      if (g) return { lat: g.lat, lng: g.lng, label: g.name.split(', ').slice(0, 3).join(', '), precise: true };
      return off;
    },
    async refine(items) {
      let changed = false;
      for (const u of items.slice(0, 8)) {
        const orig = DATA.units.find(x => x.id === u.id);
        if (orig.exact) continue;
        if (cache[u.id] === undefined) {
          const street = u.a.replace(/\bC\.?P\.?\s*\d{5}/i, '').split(/\s+(entre|por|en el|frente|junto)\s+/i)[0];
          cache[u.id] = (await nom([street, u.l, u.e].join(', '))) || (await nom([u.n, u.l, u.e].join(', ')));
        }
        const g = cache[u.id];
        if (g && km(g.lat, g.lng, orig.lat, orig.lng) < 40) { orig.lat = g.lat; orig.lng = g.lng; orig.exact = true; changed = true; }
      }
      return changed;
    }
  };
})();
