// A small stand-in for the Dashboard runtime: datasets come from the embedded JSON,
// calculations run in the order they are declared, and onData re-runs on resize and theme change.
window.dash = (() => {
  const store = { lots: window.EMBED.lots }, calcs = [], subs = [];
  const run = () => { for (const c of calcs) store[c.id] = c.fn(...c.inputs.map((i) => store[i])); };
  const colors = () => { const cs = getComputedStyle(document.documentElement); return [1, 2, 3, 4, 5, 6, 7, 8].map((i) => cs.getPropertyValue('--s' + i).trim()); };
  const api = {
    calc: (id, o) => calcs.push({ id, ...o }),
    loader: () => {},
    data: (id) => (id in store ? { status: 'ok', data: store[id], columns: [], meta: [] } : { status: 'missing', data: [] }),
    onData: (fn) => subs.push(fn),
    setLink: (id) => { try { history.replaceState(null, '', '#' + id); } catch (e) { /* the frame may refuse */ } },
    params: () => ({}), setParams: () => {}, resetParams: () => {}, refresh: () => {},
    colors: colors(),
  };
  const fire = () => { api.colors = colors(); subs.forEach((f) => f()); };
  window.addEventListener('DOMContentLoaded', () => { run(); fire(); });
  let t; window.addEventListener('resize', () => { clearTimeout(t); t = setTimeout(fire, 120); });
  try { matchMedia('(prefers-color-scheme: dark)').addEventListener('change', fire); } catch (e) { /* older browsers */ }
  new MutationObserver(fire).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  return api;
})();
