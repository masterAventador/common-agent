/* Centralized PowerAI ECG logo — a gradient pulse sweeps the load-curve waveform.
   - ease-in-out timeline (slower at the ends, quicker through the middle)
   - the moving segment has soft gradient endpoints (fades into the track) */
(function () {
  const WAVE = 'M9 25 L15.5 25 L20 13.5 L24 27 L27.5 21 L31 21';
  function ecgLogo(o) {
    o = o || {};
    const s = o.size || 40;
    const tile = o.tile;                                   // false / undefined for no tile
    const base = o.base || 'rgba(255,255,255,.24)';
    const scan = o.scan || '#4DA3FF';
    const core = o.core || '#EAF4FF';
    const dur = o.dur || 2.0;
    const glow = o.glow !== false;
    const id = 'eg' + Math.random().toString(36).slice(2, 9);
    return (
      '<svg viewBox="0 0 40 40" width="' + s + '" height="' + s + '" style="display:block;overflow:visible">' +
        '<defs><linearGradient id="' + id + '" gradientUnits="userSpaceOnUse" x1="-8" y1="0" x2="8" y2="0">' +
          '<stop offset="0" stop-color="' + scan + '" stop-opacity="0"/>' +
          '<stop offset=".42" stop-color="' + scan + '" stop-opacity="1"/>' +
          '<stop offset=".5" stop-color="' + core + '" stop-opacity="1"/>' +
          '<stop offset=".58" stop-color="' + scan + '" stop-opacity="1"/>' +
          '<stop offset="1" stop-color="' + scan + '" stop-opacity="0"/>' +
          '<animateTransform attributeName="gradientTransform" type="translate" from="0 0" to="47 0" ' +
            'dur="' + dur + 's" calcMode="spline" keyTimes="0;1" keySplines="0.42 0 0.58 1" repeatCount="indefinite"/>' +
        '</linearGradient></defs>' +
        (tile ? '<rect x="1" y="1" width="38" height="38" rx="11" fill="' + tile + '"/>' : '') +
        '<g transform="translate(20 20) scale(1.3) translate(-20 -20)">' +
        '<path d="' + WAVE + '" fill="none" stroke="' + base + '" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>' +
        '<path d="' + WAVE + '" fill="none" stroke="url(#' + id + ')" stroke-width="2.0" stroke-linecap="round" stroke-linejoin="round"' +
          (glow ? ' style="filter:drop-shadow(0 0 2.6px ' + scan + 'cc)"' : '') + '/>' +
        '</g>' +
      '</svg>'
    );
  }
  window.ecgLogo = ecgLogo;

  function init() {
    document.querySelectorAll('[data-ecg]').forEach(function (el) {
      const tile = el.getAttribute('data-tile');
      el.innerHTML = ecgLogo({
        size: +el.getAttribute('data-size') || 40,
        tile: tile === 'none' ? false : (tile || undefined),
        base: el.getAttribute('data-base') || undefined,
        scan: el.getAttribute('data-scan') || undefined,
        core: el.getAttribute('data-core') || undefined,
      });
    });
  }
  if (document.readyState !== 'loading') init();
  else document.addEventListener('DOMContentLoaded', init);
})();
