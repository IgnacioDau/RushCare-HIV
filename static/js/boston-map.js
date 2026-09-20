/* Boston map: Leaflet + CARTO tiles, no API key.
 *
 * Reuses the tile and pin styling of the Mexico module so both regions look
 * like one product. The Google path is not offered here: Boston's coordinates
 * are already exact, so there is nothing for a geocoder to improve, and asking
 * for an API key would be friction with no payoff.
 */
const BostonMap = (() => {
  let map, layer, userMarker, ready = null, lastResults = [], onPick = null;

  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const isDark = () => {
    const t = document.documentElement.getAttribute('data-theme');
    return t ? t === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  };

  function load() {
    if (ready) return ready;
    ready = new Promise((res, rej) => {
      const l = document.createElement('link');
      l.rel = 'stylesheet';
      l.href = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css';
      document.head.appendChild(l);
      const s = document.createElement('script');
      s.src = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js';
      s.onload = res;
      s.onerror = () => rej(new Error('Could not load the map. Check your connection.'));
      document.head.appendChild(s);
    });
    return ready;
  }

  let tiles;
  function setTiles() {
    if (tiles) map.removeLayer(tiles);
    const variant = isDark() ? 'dark_all' : 'light_all';
    tiles = L.tileLayer(`https://{s}.basemaps.cartocdn.com/${variant}/{z}/{x}/{y}{r}.png`, {
      maxZoom: 19, subdomains: 'abcd',
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · © <a href="https://carto.com/attributions">CARTO</a>'
    }).addTo(map);
  }

  function pinIcon(n, cls) {
    return L.divIcon({
      className: 'lpin-wrap',
      html: `<div class="lpin ${cls}">${n}</div>`,
      iconSize: [32, 32], iconAnchor: [16, 16]
    });
  }

  function setUser(lat, lon, quiet) {
    if (!map) return;
    if (userMarker) userMarker.setLatLng([lat, lon]);
    else {
      userMarker = L.marker([lat, lon], {
        icon: L.divIcon({ className: 'lpin-wrap', html: '<div class="luser"></div>', iconSize: [22, 22], iconAnchor: [11, 11] }),
        draggable: true, zIndexOffset: 1000
      }).addTo(map).bindTooltip('You');
      // Dragging is the whole point of the pin: someone who knows the city can
      // place themselves precisely without typing an address into a geocoder.
      userMarker.on('dragend', () => {
        const p = userMarker.getLatLng();
        if (onPick) onPick(p.lat, p.lng, 'pin');
      });
    }
    if (!quiet && onPick) onPick(lat, lon, 'pin');
  }

  function paint(results) {
    lastResults = results || [];
    if (!map) return;
    layer.clearLayers();
    const pts = [];
    if (userMarker) pts.push([userMarker.getLatLng().lat, userMarker.getLatLng().lng]);
    lastResults.forEach((r, i) => {
      if (r.lat == null) return;
      const cls = (i === 0 ? 'first ' : '') + (r.flags && r.flags.unverified ? 'approx' : '');
      L.marker([r.lat, r.lon], { icon: pinIcon(i + 1, cls), zIndexOffset: 500 - i })
        .bindTooltip(r.name, { direction: 'top', offset: [0, -14] })
        .on('click', () => window.dispatchEvent(new CustomEvent('map-select', { detail: r.id })))
        .addTo(layer);
      pts.push([r.lat, r.lon]);
    });
    if (pts.length > 1) map.fitBounds(pts, { padding: [60, 60], maxZoom: 15 });
    else if (pts.length === 1) map.setView(pts[0], 14);
  }

  return {
    async init(el, pickHandler) {
      onPick = pickHandler;
      await load();
      map = L.map(el, { zoomControl: true, minZoom: 10 }).setView([42.3467, -71.0972], 12);
      layer = L.layerGroup().addTo(map);
      setTiles();
      map.on('click', e => setUser(e.latlng.lat, e.latlng.lng));
      new MutationObserver(() => { setTiles(); paint(lastResults); })
        .observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
      new ResizeObserver(() => map.invalidateSize()).observe(el);
    },
    setUser,
    update: paint
  };
})();
