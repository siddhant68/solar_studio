// Ordinary Playwright runtime probes of the locally built agrivoltaic reference.
//
// These complement the REA `capture_browser_scenario` runs: REA retains screenshots, DOM
// and a SHA-256 of each localStorage value, but not the stored design itself. This probe
// reads control values through the live input property, the readouts, and the stored
// design JSON. Its output is labelled Playwright runtime evidence, never REA Evidence.
//
//   node agv_playwright_scenarios.cjs http://127.0.0.1:4173/ OUT_DIR
//
// Every non-loopback request is aborted and recorded; the bundled example garden is
// served from the local build, so no external service response is observed or mocked.
const fs = require('fs')
const path = require('path')
const crypto = require('crypto')
const { chromium } = require('playwright')

const base = process.argv[2]
const out = process.argv[3]
fs.mkdirSync(out, { recursive: true })

const CONTROLS = [
  'control-array-tilt', 'control-array-azimuth', 'control-array-pitch',
  'control-array-collector-width', 'control-array-clearance', 'control-array-row-azimuth',
  'control-array-row-count', 'control-array-modules-per-row', 'control-array-module-width',
  'control-array-module-height', 'control-array-module-power',
]

const sha = (buf) => crypto.createHash('sha256').update(buf).digest('hex')

async function openPanels(page) {
  await page.getByTestId('action-step-panels').click()
  const fold = page.getByTestId('details-panels-by-hand')
  if ((await fold.getAttribute('open')) === null) await fold.locator('summary').first().click()
  await page.getByTestId('control-array-row-count').waitFor({ state: 'visible' })
}

async function observe(page, label, record) {
  const controls = {}
  for (const id of CONTROLS) controls[id] = await page.getByTestId(id).inputValue()
  const readouts = await page.$$eval('[data-testid^="readout-array-"]', (els) =>
    Object.fromEntries(els.filter((e) => !e.dataset.testid.endsWith('-help'))
      .map((e) => [e.dataset.testid, e.textContent.trim()])))
  const stored = await page.evaluate(() => localStorage.getItem('agrivoltaic-garden-designer/design'))
  let storedArrays = null
  let storedKeys = null
  if (stored) {
    const env = JSON.parse(stored)
    const design = env.design ?? env.payload ?? env
    storedKeys = Object.keys(design)
    const plot = design.plot ?? null
    storedArrays = plot ? plot.arrays.map((a) => ({ id: a.id, geometry: a.geometry, tracker: a.tracker, module: { widthM: a.module.widthM, heightM: a.module.heightM, nameplateWp: a.module.nameplateWp }, derived: a.derived ?? null })) : null
  }
  const energy = await page.getByTestId('status-energy').getAttribute('data-state').catch(() => null)
  const png = await page.screenshot()
  const file = `${record.name}-${label}.png`
  fs.writeFileSync(path.join(out, file), png)
  record.observations.push({
    label, controls, readouts, energy_status: energy,
    stored_design_sha256: stored ? sha(Buffer.from(stored, 'utf8')) : null,
    stored_design_top_level_keys: storedKeys, stored_arrays: storedArrays,
    screenshot: { file, sha256: sha(png), bytes: png.length },
  })
}

async function scenario(browser, name, body) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, locale: 'en-US', timezoneId: 'UTC' })
  const page = await context.newPage()
  const record = { name, aborted_external_requests: [], console_errors: 0, observations: [], steps: [] }
  await page.route(/^https?:\/\/(?!localhost|127\.0\.0\.1)/i, (r) => { record.aborted_external_requests.push(r.request().url().split('?')[0]); r.abort() })
  page.on('console', (m) => { if (m.type() === 'error') record.console_errors += 1 })
  await page.goto(base, { waitUntil: 'load' })
  await page.getByTestId('app-root').waitFor({ state: 'visible' })
  await page.waitForTimeout(5000)
  const step = async (label, fn) => { await fn(); record.steps.push(label) }
  await body(page, record, step)
  record.aborted_external_requests = [...new Set(record.aborted_external_requests)]
  await context.close()
  return record
}

;(async () => {
  const browser = await chromium.launch()
  const results = []
  results.push(await scenario(browser, 'S1-small-array', async (page, rec, step) => {
    await step('open panels', () => openPanels(page))
    await observe(page, 'before', rec)
    await step('rows=2', () => page.getByTestId('control-array-row-count').fill('2'))
    await step('modules per row=4', () => page.getByTestId('control-array-modules-per-row').fill('4'))
    await page.waitForTimeout(1500)
    await observe(page, 'after', rec)
  }))
  results.push(await scenario(browser, 'S2-change-pitch-tilt', async (page, rec, step) => {
    await step('open panels', () => openPanels(page))
    await observe(page, 'before', rec)
    await step('pitch=6', () => page.getByTestId('control-array-pitch').fill('6'))
    await page.waitForTimeout(500)
    await observe(page, 'after-pitch', rec)
    await step('tilt=35', () => page.getByTestId('control-array-tilt').fill('35'))
    await page.waitForTimeout(1500)
    await observe(page, 'after-tilt', rec)
  }))
  results.push(await scenario(browser, 'S3-save-reload', async (page, rec, step) => {
    await step('open panels', () => openPanels(page))
    await step('tilt=33', () => page.getByTestId('control-array-tilt').fill('33'))
    await step('pitch=7.5', () => page.getByTestId('control-array-pitch').fill('7.5'))
    await page.waitForTimeout(500)
    await step('save', async () => {
      await page.getByTestId('action-step-check').click()
      await page.getByTestId('action-storage-save').click()
      await page.waitForTimeout(1500)
    })
    rec.storage_status_before_reload = await page.getByTestId('status-storage').getAttribute('data-state')
    await step('back to panels', () => openPanels(page))
    await observe(page, 'saved-before-reload', rec)
    await step('reload', async () => {
      await page.reload({ waitUntil: 'load' })
      await page.getByTestId('app-root').waitFor({ state: 'visible' })
      await page.waitForTimeout(5000)
    })
    await page.getByTestId('action-step-check').click()
    rec.storage_status_after_reload = await page.getByTestId('status-storage').getAttribute('data-state')
    await step('reopen panels', () => openPanels(page))
    await observe(page, 'after-reload', rec)
  }))
  await browser.close()
  fs.writeFileSync(path.join(out, 'playwright-scenarios.json'), JSON.stringify({
    authority: 'ordinary Playwright runtime observation (not REA Evidence)',
    playwright_version: require('playwright/package.json').version,
    base_url: base, results,
  }, null, 1))
  console.log(JSON.stringify(results.map((r) => ({ name: r.name, observations: r.observations.length, aborted: r.aborted_external_requests.length }))))
})().catch((e) => { console.error(e); process.exit(1) })
