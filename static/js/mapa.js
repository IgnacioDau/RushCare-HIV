/* ---------- selector de mapa ----------
   Solo existe la implementación de Leaflet + OpenStreetMap: no requiere
   clave, no requiere configuración, y ya cubre lo que la vista embebida de
   Google hacía. Direcciones a un sitio puntual se resuelven aparte, con un
   link de Google Maps normal (ver dirHref en mexico.js) — no hace falta
   embeber el mapa de Google para eso. */
const MapAdapter = {
  async init(el) {
    try { await LeafletImpl.init(el); }
    catch (e) { setStatus(esc(e.message), true); }
  },
  update: s => LeafletImpl.update(s),
  select: id => LeafletImpl.select(id)
};
const Geo = {
  geocode: q => LeafletGeo.geocode(q),
  refine: items => LeafletGeo.refine(items)
};
/* ---------- Mapa de calles con Leaflet + OpenStreetMap (sin clave) ----------
   CARTO dejó de ofrecer tiles gratis sin clave; OSM estándar sí sigue siendo gratis.
   Los tiles se muestran sin filtro: un mapa teñido se ve mejor como página y
   peor como mapa, y aquí lo único que importa es que se lea. */
const LeafletImpl = (() => {
  let map, layer, markers = new Map(), lastS = null, ready = null;
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  function load() {
    if (ready) return ready;
    ready = new Promise((res, rej) => {
      const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css'; document.head.appendChild(l);
      const s = document.createElement('script'); s.src = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js'; s.onload = res; s.onerror = () => rej(new Error('No se pudo cargar el mapa. Revisa tu conexión.')); document.head.appendChild(s);
    });
    return ready;
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
      layer = L.layerGroup().addTo(map);
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19, attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
      }).addTo(map);
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
