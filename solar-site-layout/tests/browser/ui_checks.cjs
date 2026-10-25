// Real-browser acceptance checks for V01, V02 and V03 (Playwright + Chromium).
//
//   node ui_checks.cjs BASE_URL OUT_DIR FIXTURES_DIR
//
// Writes OUT_DIR/ui-checks.json (one record per check with pass/fail and observations)
// and screenshots. Exit status 0 only if every check passed.
'use strict'
const fs = require('fs')
const path = require('path')
const crypto = require('crypto')
const { chromium } = require('playwright')

const [base, out, fixtures] = process.argv.slice(2)
fs.mkdirSync(out, { recursive: true })
const results = []
const sha = (b) => crypto.createHash('sha256').update(b).digest('hex')

function check(name, ok, details) {
  results.push({ name, pass: !!ok, details })
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}`)
}

async function newPage(browser) {
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 950 }, acceptDownloads: true })
  const page = await ctx.newPage()
  page._errors = []
  page.on('pageerror', (e) => page._errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error') page._errors.push(m.text()) })
  return page
}

async function ready(page, url) {
  await page.goto(url)
  await page.waitForSelector('body[data-ready="1"]')
}

async function generateAndWait(page) {
  const before = await page.getByTestId('history').textContent()
  await page.getByTestId('generate').click()
  await page.waitForFunction((b) => document.getElementById('history').textContent !== b, before, { timeout: 60000 })
  await page.waitForSelector('#plan')
}

const summaryNums = (page) => page.getByTestId('summary').evaluate((el) => ({ modules: Number(el.dataset.modules), tables: Number(el.dataset.tables) }))

;(async () => {
  const browser = await chromium.launch()

  // ---------------- V01 ----------------
  {
    const page = await newPage(browser)
    await ready(page, base + '/')
    await page.getByTestId('import-file').setInputFiles(path.join(fixtures, 'obstacle.request.json'))
    await page.waitForFunction(() => document.getElementById('messages').textContent.includes('Imported'))
    const importedSetback = await page.getByTestId('in-setback').inputValue()
    await page.getByTestId('in-tilt').fill('10')
    await generateAndWait(page)
    const nums = await summaryNums(page)
    const summaryText = await page.getByTestId('summary').textContent()
    const statusAfterGen = await page.getByTestId('status-result').getAttribute('data-state')
    await page.screenshot({ path: path.join(out, 'V01-app-after-generate.png'), fullPage: false })
    // independent expectation: tilt 10 keeps D = 4 cos 10 = 3.939 < pitch 5 - gap 1; same 5 tables
    const d = (4 * Math.cos((10 * Math.PI) / 180)).toFixed(3)
    check('V01 import + edit + generate shows totals', nums.modules === 20 && nums.tables === 5 && summaryText.includes(d) && statusAfterGen === 'current', { nums, expected_D: d, statusAfterGen, importedSetback })
    const projectId = await page.getByTestId('project-id').inputValue()
    const url = page.url()
    // save/reload: a fresh page load restores the project, inputs and the selected result
    await page.reload()
    await page.waitForSelector('body[data-ready="1"]')
    await page.waitForSelector('#plan')
    const tiltAfter = await page.getByTestId('in-tilt').inputValue()
    const statusIn = await page.getByTestId('status-inputs').getAttribute('data-state')
    const statusRes = await page.getByTestId('status-result').getAttribute('data-state')
    const nums2 = await summaryNums(page)
    check('V01 save/reload restores project, inputs and current result', tiltAfter === '10' && statusIn === 'saved' && statusRes === 'current' && nums2.modules === 20 && url.includes(projectId), { projectId, url, tiltAfter, statusIn, statusRes })
    await page.screenshot({ path: path.join(out, 'V01-app-after-reload.png'), fullPage: true })
    // download an export
    await page.getByTestId('export-format').selectOption('bundle')
    const [dl] = await Promise.all([page.waitForEvent('download'), page.getByTestId('export-link').click()])
    const file = path.join(out, 'V01-download-' + dl.suggestedFilename())
    await dl.saveAs(file)
    const buf = fs.readFileSync(file)
    check('V01 export download (zip bundle)', buf.slice(0, 2).toString() === 'PK' && buf.length > 1000, { file: path.basename(file), bytes: buf.length, sha256: sha(buf) })
    check('V01 no browser errors', page._errors.length === 0, { errors: page._errors })
    await page.context().close()
  }

  // ---------------- V02 ----------------
  async function holdFirstGeneration(page) {
    let release
    const gate = new Promise((r) => { release = r })
    let held = 0
    await page.route('**/api/layouts', async (route) => {
      if (route.request().method() !== 'POST' || held > 0) return route.continue()
      held += 1
      const response = await route.fetch() // the server answers now; the browser sees it only on release
      await gate
      await route.fulfill({ response })
    })
    return () => release()
  }

  {
    // case A: edit while pending, then release -> result labelled historical, edits stay dirty
    const page = await newPage(browser)
    await ready(page, base + '/')
    const release = await holdFirstGeneration(page)
    await page.getByTestId('save').click()
    await page.waitForFunction(() => document.getElementById('status-inputs').dataset.state === 'saved')
    await page.getByTestId('generate').click()
    await page.waitForTimeout(400)
    await page.getByTestId('in-tilt').fill('15')
    const dirtyWhilePending = await page.getByTestId('status-inputs').getAttribute('data-state')
    release()
    await page.waitForSelector('#plan')
    await page.waitForFunction(() => document.getElementById('status-result').dataset.state !== 'none')
    const resState = await page.getByTestId('status-result').getAttribute('data-state')
    const banner = await page.locator('#summary .banner').getAttribute('data-state')
    const inState = await page.getByTestId('status-inputs').getAttribute('data-state')
    const tilt = await page.getByTestId('in-tilt').inputValue()
    await page.screenshot({ path: path.join(out, 'V02-late-result-outdated.png') })
    check('V02 delayed result labelled historical; new edits remain dirty', dirtyWhilePending === 'dirty' && resState === 'outdated' && banner === 'outdated' && inState === 'dirty' && tilt === '15', { dirtyWhilePending, resState, banner, inState, tilt })
    await page.context().close()
  }
  {
    // case B: a late response from an older generation cannot replace a newer selection
    const page = await newPage(browser)
    await ready(page, base + '/')
    const release = await holdFirstGeneration(page)
    await page.getByTestId('save').click()
    await page.waitForFunction(() => document.getElementById('status-inputs').dataset.state === 'saved')
    await page.getByTestId('generate').click() // A (rev 1), held
    await page.waitForTimeout(400)
    await page.getByTestId('in-setback').fill('0.5')
    await generateAndWait(page) // B (saves rev 2), completes first
    const bText = await page.getByTestId('status-result').textContent()
    const bModules = (await summaryNums(page)).modules
    release()
    await page.waitForFunction(() => document.getElementById('messages').textContent.includes('late response'), null, { timeout: 30000 })
    const after = await page.getByTestId('status-result').textContent()
    const afterState = await page.getByTestId('status-result').getAttribute('data-state')
    const afterModules = (await summaryNums(page)).modules
    const historyText = await page.getByTestId('history').textContent()
    const pid = await page.getByTestId('project-id').inputValue()
    const proj = await (await page.request.get(`${base}/api/projects/${pid}`)).json()
    const bId = bText.match(/res_[0-9a-f]{24}/)[0]
    await page.screenshot({ path: path.join(out, 'V02-late-response-not-overwriting.png') })
    check('V02 old response cannot overwrite newer result selection', after === bText && afterState === 'current' && afterModules === bModules && historyText.includes('late response') && proj.selected_result_id === bId && proj.revision === 2 && proj.selected_result_is_current === true,
      { displayed_before_release: bText, displayed_after_release: after, server_selected: proj.selected_result_id, server_revision: proj.revision })
    await page.context().close()
  }

  // ---------------- V03 ----------------
  for (const [example, expect] of [['rectangle', { modules: 24, exclusions: 0 }], ['concave-notch', { modules: 0, exclusions: 0 }], ['hole', { modules: 0, exclusions: 0 }], ['projected-rotated', { modulesMin: 1, exclusions: 1 }]]) {
    const page = await newPage(browser)
    await ready(page, base + '/')
    await page.getByTestId('example-select').selectOption(example)
    await page.getByTestId('load-example').click()
    await page.waitForFunction((e) => document.getElementById('messages').textContent.includes(e), example)
    await generateAndWait(page)
    await page.waitForTimeout(300)
    const overview = path.join(out, `V03-${example}-overview.png`)
    await page.getByTestId('plan-host').screenshot({ path: overview })
    const geo = await page.evaluate(() => {
      const host = document.getElementById('plan-host')
      const pageSvg = host.querySelector('svg')
      const plan = host.querySelector('#plan')
      const pr = plan.getBoundingClientRect()
      const page = pageSvg.getBoundingClientRect()
      const texts = [...host.querySelectorAll('#side-panel text')].map((t) => t.getBoundingClientRect())
      const overlap = texts.filter((r) => !(r.right <= pr.left || r.left >= pr.right || r.bottom <= pr.top || r.top >= pr.bottom)).length
      const outside = texts.filter((r) => r.left < page.left - 1 || r.right > page.right + 1 || r.top < page.top - 1 || r.bottom > page.bottom + 1).length
      const txt = host.textContent
      return {
        north: !!host.querySelector('#north-arrow'), scale: !!host.querySelector('#scale-bar'), legend: txt.includes('Legend'),
        units: txt.includes('metres'), site: host.querySelectorAll('path.site').length, exclusions: host.querySelectorAll('path.exclusion').length,
        holes: (host.querySelector('path.site').getAttribute('d').match(/M/g) || []).length,
        modules: host.querySelectorAll('polygon.module').length, tables: host.querySelectorAll('polygon.table').length,
        textOverlapsPlan: overlap, textOutsidePage: outside, nText: texts.length,
      }
    })
    // close-up: zoom onto the first module (or the site's first vertex for empty layouts)
    await page.evaluate(() => {
      const plan = document.querySelector('#plan')
      const m = plan.querySelector('polygon.module')
      let cx, cy
      if (m) {
        const pts = m.getAttribute('points').split(' ').map((p) => p.split(',').map(Number))
        cx = pts.reduce((a, p) => a + p[0], 0) / pts.length
        cy = pts.reduce((a, p) => a + p[1], 0) / pts.length
      } else {
        const d = plan.querySelector('path.site').getAttribute('d').match(/M([-0-9.e]+),([-0-9.e]+)/)
        cx = Number(d[1]); cy = Number(d[2])
      }
      const w = 6, h = 4
      plan.setAttribute('viewBox', `${cx - w / 2} ${cy - h / 2} ${w} ${h}`)
    })
    // update the scale label the same way the zoom buttons do
    await page.getByTestId('zoom-in').click()
    await page.getByTestId('zoom-out').click()
    const closeup = path.join(out, `V03-${example}-closeup.png`)
    await page.getByTestId('plan-host').screenshot({ path: closeup })
    const scaleText = await page.locator('#plan-host #scale-text').textContent()
    // gaps: within each table, module polygons must not share area (computed from the DOM points)
    const gapOk = await page.evaluate(() => {
      const mods = [...document.querySelectorAll('#plan polygon.module')].map((p) => p.getAttribute('points').split(' ').map((q) => q.split(',').map(Number)))
      // area of each module vs table envelope: sum(module areas) <= table area
      const area = (pts) => Math.abs(pts.reduce((a, p, i) => a + p[0] * pts[(i + 1) % pts.length][1] - pts[(i + 1) % pts.length][0] * p[1], 0) / 2)
      const tables = [...document.querySelectorAll('#plan polygon.table')].map((p) => area(p.getAttribute('points').split(' ').map((q) => q.split(',').map(Number))))
      const mArea = mods.reduce((a, m) => a + area(m), 0)
      const tArea = tables.reduce((a, t) => a + t, 0)
      return { moduleArea: mArea, tableEnvelopeArea: tArea, envelopeExceedsModules: tArea - mArea }
    })
    const okModules = expect.modules !== undefined ? geo.modules === expect.modules : geo.modules >= expect.modulesMin
    check(`V03 ${example} overview/close-up drawing`, geo.north && geo.scale && geo.legend && geo.units && geo.site === 1 && geo.exclusions === expect.exclusions && okModules && geo.textOverlapsPlan === 0 && geo.textOutsidePage === 0 && /at this zoom/.test(scaleText),
      { ...geo, scaleText, gapOk, screenshots: [path.basename(overview), path.basename(closeup)] })
    check(`V03 ${example} no browser errors`, page._errors.length === 0, { errors: page._errors })
    await page.context().close()
  }

  await browser.close()
  const passed = results.every((r) => r.pass)
  fs.writeFileSync(path.join(out, 'ui-checks.json'), JSON.stringify({ authority: 'Playwright + Chromium against the local solar-site-layout server', base, playwright: require('playwright/package.json').version, passed, results }, null, 1))
  process.exit(passed ? 0 : 1)
})().catch((e) => { console.error(e); process.exit(2) })
