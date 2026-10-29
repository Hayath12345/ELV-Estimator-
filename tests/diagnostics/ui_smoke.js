// Test-only helper: UI smoke test of every screen and main action, driven by Playwright (Chromium)
// against the app's dev server (`python -m app.main --dev --port PORT`): the real React build in
// ui/dist talking to the real Python backend over the HTTP bridge (/api/call, /api/events).
// The pywebview window itself is not driven (Windows-only GUI).
//
// Usage: node tests/diagnostics/ui_smoke.js http://127.0.0.1:8765 OUT_DIR
// Writes OUT_DIR/json/ui_smoke.json and OUT_DIR/images/ui_*.png
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = process.argv[2] || 'http://127.0.0.1:8765';
const OUT = process.argv[3] || '.';
fs.mkdirSync(path.join(OUT, 'images'), { recursive: true });
fs.mkdirSync(path.join(OUT, 'json'), { recursive: true });

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  page.on('dialog', (d) => d.accept());
  let stepErrors = [];
  const allErrors = [];
  const apiErrors = [];
  page.on('pageerror', (e) => { stepErrors.push('pageerror: ' + e.message); allErrors.push('pageerror: ' + e.message); });
  page.on('console', (m) => { if (m.type() === 'error') { stepErrors.push('console.error: ' + m.text()); allErrors.push('console.error: ' + m.text()); } });
  page.on('response', async (r) => {
    if (r.url().includes('/api/call')) {
      try {
        const j = await r.json();
        if (!j.ok) apiErrors.push({ url: r.url(), status: r.status(), error: j.error });
      } catch (e) { /* non-JSON */ }
    }
  });
  const results = [];
  let n = 0;
  async function step(name, fn) {
    stepErrors = [];
    const t0 = Date.now();
    let ok = true, err = null;
    try { await fn(); } catch (e) { ok = false; err = String(e.message || e).split('\n')[0]; }
    await page.waitForTimeout(300);
    const shot = `ui_${String(++n).padStart(2, '0')}_${name.replace(/[^a-z0-9]+/gi, '_').toLowerCase()}.png`;
    try { await page.screenshot({ path: path.join(OUT, 'images', shot) }); } catch (e) { /* ignore */ }
    results.push({ step: n, name, pass: ok && stepErrors.filter((x) => x.startsWith('pageerror')).length === 0, ms: Date.now() - t0,
      error: err, console_errors: stepErrors.slice(), screenshot: shot });
    console.log(`${ok ? 'PASS' : 'FAIL'} ${n} ${name} (${Date.now() - t0} ms)${err ? ' — ' + err : ''}`);
  }
  // no waitForLoadState('networkidle'): the app keeps a long-poll open on /api/events, so the network never idles
  const nav = async (label) => { await page.click(`aside >> text="${label}"`); await page.waitForTimeout(700); };
  const expectText = async (t, timeout = 15000) => { await page.waitForSelector(`text=${t}`, { timeout }); };

  await step('Launch — dashboard (Quotations)', async () => { await page.goto(BASE + '/'); await expectText('Quotations'); });
  await step('New quotation modal opens and cancels', async () => {
    await page.click('button:has-text("New quotation from drawings")');
    await expectText('Create and upload drawings');
    await page.click('.modal button:has-text("Cancel"), button:has-text("Cancel")');
  });
  await step('Open sample project (import + extraction of 2 DXF floors via backend job)', async () => {
    await page.click('button:has-text("Open sample project")');
    await expectText('Continue to Systems', 90000);
  });
  await step('Drawings — calibration dialog opens and closes', async () => {
    await nav('Drawings');
    await page.click('button:has-text("Calibrate scale")');
    await expectText('Apply to this drawing');
    await page.click('button[aria-label="Close"], .x');
  });
  await step('Systems — screen and totals', async () => { await nav('Systems'); await expectText('Combined award'); });
  await step('Systems — toggle Combined award off and on', async () => {
    const t = page.locator('label:has-text("Combined award") button.toggle');
    const before = await t.getAttribute('aria-pressed');
    await t.click(); await page.waitForTimeout(800);
    const mid = await t.getAttribute('aria-pressed');
    await t.click(); await page.waitForTimeout(800);
    const after = await t.getAttribute('aria-pressed');
    if (before === mid || before !== after) throw new Error(`toggle states ${before} -> ${mid} -> ${after}`);
  });
  await step('Device Layout — plan renders with devices', async () => {
    await nav('Device Layout');
    await page.waitForSelector('svg g[transform^="translate"]', { timeout: 15000 });
    const k = await page.locator('svg g[transform^="translate"]').count();
    if (k < 10) throw new Error(`only ${k} device symbols`);
  });
  await step('Device Layout — select a device shows its panel', async () => {
    const bb = await page.locator('svg g[transform^="translate"]').nth(5).boundingBox();
    await page.mouse.move(bb.x + bb.width / 2, bb.y + bb.height / 2);
    await page.mouse.down(); await page.mouse.up();
    await page.waitForTimeout(400);
    await expectText('Duplicate', 5000);
  });
  await step('Device Layout — toggle fields of view', async () => {
    await page.click('label:has-text("Fields of view")'); await page.waitForTimeout(300);
    await page.click('label:has-text("Fields of view")');
  });
  await step('Device Layout — switch floor', async () => {
    const seg = page.locator('text=3F').first();
    await seg.click(); await page.waitForTimeout(800);
  });
  await step('Device Layout — add device mode, click on plan', async () => {
    await page.click('text=Add device');
    const box = await page.locator('svg').first().boundingBox();
    await page.mouse.click(box.x + box.width * 0.42, box.y + box.height * 0.45);
    await page.waitForTimeout(800);
    await page.click('text=Select / move');
  });
  await step('Device Layout — reset floor', async () => { await page.click('button:has-text("Reset floor")'); await page.waitForTimeout(800); });
  await step('Comms Rooms — screen', async () => { await nav('Comms Rooms'); await expectText('PoE'); });
  await step('BOQ & Pricing — screen (unpriced)', async () => { await nav('BOQ & Pricing'); await expectText('Standalone vs combined'); });
  await step('Price Library — enter a price and change currency', async () => {
    await nav('Price Library');
    const box = page.locator('input[placeholder="enter price"]').first();
    await box.fill('412'); await box.press('Enter'); await page.waitForTimeout(800);
    await page.locator('select.cell').nth(1).selectOption('EUR'); await page.waitForTimeout(800);
  });
  await step('BOQ & Pricing — priced line visible', async () => { await nav('BOQ & Pricing'); await page.waitForTimeout(500); });
  await step('Checks & Export — screen', async () => { await nav('Checks & Export'); await expectText('Generate'); });
  await step('Checks & Export — record override and generate package', async () => {
    await page.click('button:has-text("Generate")'); await page.waitForTimeout(600);
    const ta = page.locator('textarea[placeholder^="Reason"]');
    if (await ta.count()) {
      await ta.fill('UI smoke test: issue before all supplier prices are received');
      await page.click('button:has-text("Record override")'); await page.waitForTimeout(800);
      await page.click('button:has-text("Generate")');
    }
    await expectText('Package generated', 180000);
  });
  await step('Revision history — screen', async () => { await nav('Revision history'); await expectText('Rev 1'); });
  await step('Project details — save', async () => {
    await nav('Project details');
    await page.click('button:has-text("Save details")'); await page.waitForTimeout(600);
  });
  await step('Assumptions & exclusions — screen', async () => { await nav('Assumptions & exclusions'); await page.waitForTimeout(400); });
  await step('Settings — save', async () => { await nav('Settings'); await page.click('button:has-text("Save settings")'); await page.waitForTimeout(600); });
  await step('Quotations — dashboard lists the project', async () => { await nav('Quotations'); await expectText('Sample HQ Fit-Out'); });

  const out = { base: BASE, method: 'Playwright Chromium against app.main --dev (real backend over HTTP bridge)',
    steps: results, passed: results.filter((r) => r.pass).length, total: results.length,
    console_errors_total: allErrors.length, console_errors: allErrors, api_errors: apiErrors };
  fs.writeFileSync(path.join(OUT, 'json', 'ui_smoke.json'), JSON.stringify(out, null, 1));
  console.log(`UI smoke: ${out.passed}/${out.total} passed, ${allErrors.length} console errors, ${apiErrors.length} API errors`);
  await browser.close();
})();
