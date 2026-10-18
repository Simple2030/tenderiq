// Screenshot dashboard/index.html at desktop and phone width, light and dark.
// Usage: node dashboard/shoot.js <outdir>   -> prints console errors and overflow
const { chromium } = require('/opt/node22/lib/node_modules/playwright');
const fs = require('fs'), path = require('path');
const out = process.argv[2] || '.';
(async () => {
  const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
  const doc = '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body dir="rtl">' + html + '</body></html>';
  const b = await chromium.launch();
  for (const [w, h, scheme, name, expand] of [
    [1440, 900, 'light', 'desktop', false], [1440, 900, 'light', 'desktop-full', true],
    [400, 860, 'light', 'mobile', false], [1440, 900, 'dark', 'desktop-dark', false]]) {
    const p = await b.newPage({ viewport: { width: w, height: h }, colorScheme: scheme });
    const errs = [];
    p.on('pageerror', e => errs.push(e.message));
    p.on('console', m => { if (m.type() === 'error' && !/ERR_CERT|fonts/.test(m.text())) errs.push(m.text()); });
    await p.setContent(doc); await p.waitForTimeout(500);
    if (expand) { await p.click('tr.lot'); await p.waitForTimeout(200); }
    await p.screenshot({ path: path.join(out, name + '.png'), fullPage: expand });
    const ov = await p.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    console.log(name, 'errors:', JSON.stringify(errs), 'horizontalOverflow:', ov);
  }
  await b.close();
})();
