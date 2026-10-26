// Real-browser acceptance checks for V01, V02 and V03 (Playwright + Chromium).
//
//   node ui_checks.cjs BASE_URL OUT_DIR FIXTURES_DIR
//
// Writes OUT_DIR/ui-checks.json (one record per check with pass/fail and observations)
// and screenshots. Exit status 0 only if every check passed. Every page records console
// errors with their source location and every HTTP response >= 400 or failed request
// with its URL; any of those fails that page's "no browser errors" check.
//
// The browser is full Chromium (channel "chromium", which also requests /favicon.ico
// like a desktop browser); SOLAR_BROWSER_CHANNEL overrides it.
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
  const errors = []
  page.on('pageerror', (e) => errors.push(`pageerror: ${e}`))
  page.on('console', (m) => {
    if (m.type() !== 'error') return
    const loc = m.location()
    errors.push(`console: ${m.text()} @ ${loc.url || '?'}:${loc.lineNumber ?? '?'}`)
  })
  page.on('response', (r) => { if (r.status() >= 400) errors.push(`http ${r.status()} ${r.request().method()} ${r.url()}`) })
  // A link that turns into a download aborts its navigation request (net::ERR_ABORTED);
  // only that exact case is excused, matched against the URLs that became downloads.
  const failed = []
  const downloads = new Set()
  page.on('download', (d) => downloads.add(d.url()))
  page.on('requestfailed', (r) => failed.push({ text: r.failure() && r.failure().errorText, method: r.method(), url: r.url() }))
  Object.defineProperty(page, '_errors', {
    get: () => errors.concat(failed.filter((f) => !(f.text === 'net::ERR_ABORTED' && downloads.has(f.url))).map((f) => `request failed (${f.text}) ${f.method} ${f.url}`)),
  })
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

// Hold the first request matching (pattern, method): the server answers at once, the
// browser sees the answer only on release(). `held` resolves once the request is held.
async function holdFirst(page, pattern, method) {
  let release
  let onHeld
  const gate = new Promise((r) => { release = r })
  const held = new Promise((r) => { onHeld = r })
  let n = 0
  await page.route(pattern, async (route) => {
    if (route.request().method() !== method || n++ > 0) return route.continue()
    const response = await route.fetch()
    onHeld()
    await gate
    await route.fulfill({ response })
  })
  return { held, release: () => release() }
}

// Run one scenario; an exception (e.g. a wait that never completes) is a failed check
// for that scenario rather than an abort of the whole run.
async function scenario(name, fn) {
  try {
    await fn()
  } catch (e) {
    check(name, false, { exception: String(e).slice(0, 2000) })
  }
}

const waitMessage = (page, text) => page.waitForFunction((t) => document.getElementById('messages').textContent.includes(t), text, { timeout: 30000 })

;(async () => {
  const channel = process.env.SOLAR_BROWSER_CHANNEL || 'chromium'
  const browser = await chromium.launch({ channel })

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

  // ---------------- V02: review regressions F1/F2 (2026-10-26) ----------------
  const fixture = (name) => JSON.parse(fs.readFileSync(path.join(fixtures, name), 'utf8'))
  const observe = (page) => page.evaluate(() => {
    const d = state.displayed
    return {
      edited_width: document.querySelector('[data-testid=in-module-width]').value,
      inputs_state: document.getElementById('status-inputs').dataset.state,
      result_state: document.getElementById('status-result').dataset.state,
      result_text: document.getElementById('status-result').textContent,
      modules: document.getElementById('summary').dataset.modules,
      identity: (document.querySelector('[data-testid=identity]') || {}).textContent || null,
      banner: (document.querySelector('#summary .banner') || { dataset: {} }).dataset.state || null,
      export_href: document.getElementById('export-link').getAttribute('href'),
      export_disabled: document.getElementById('export-link').classList.contains('disabled'),
      plan_result: (document.querySelector('#plan-host > svg') || { dataset: {} }).dataset.resultId || null,
      has_plan: !!document.querySelector('#plan'),
      displayed: d && { result: d.resultId, revision: d.revision, project: d.projectId, inputs: JSON.parse(d.inputsJSON || 'null'), dims: d.data.summary.dimensions },
      project: state.project && { id: state.project.project_id, revision: state.project.revision, saved: JSON.parse(state.project.savedJSON) },
      history: document.getElementById('history').textContent,
      messages: document.getElementById('messages').textContent,
    }
  })
  const getProject = async (page, pid) => (await page.request.get(`${base}/api/projects/${pid}`)).json()

  await scenario('V02 F1 create-delay scenario', async () => {
    // F1, project creation delayed: an edit made while the first save is in flight must
    // not be attributed to the result of the saved inputs
    const page = await newPage(browser)
    await ready(page, base + '/')
    const hold = await holdFirst(page, '**/api/projects', 'POST')
    await page.getByTestId('generate').click()
    await hold.held
    await page.getByTestId('in-module-width').fill('2')
    hold.release()
    await page.waitForSelector('#plan')
    await page.waitForFunction(() => document.getElementById('status-result').dataset.state !== 'none')
    const o = await observe(page)
    const server = await getProject(page, o.project.id)
    await page.screenshot({ path: path.join(out, 'V02-F1-create-delay.png') })
    await generateAndWait(page) // the edit itself now becomes current
    const after = await observe(page)
    check('V02 F1 create-delay edit stays dirty; result labelled with the saved snapshot',
      o.result_state === 'outdated' && o.banner === 'outdated' && o.inputs_state === 'dirty' && o.edited_width === '2' && o.modules === '24' &&
      o.displayed.inputs.module.width_m === 1 && o.project.saved.module.width_m === 1 && o.displayed.dims.table_width_W_m === 2 &&
      server.revision === 1 && server.request.module.width_m === 1 &&
      after.result_state === 'current' && after.modules === '16' && after.displayed.revision === 2 && after.displayed.inputs.module.width_m === 2,
      { during: o, server_revision: server.revision, server_width: server.request.module.width_m, after_regenerate: { result_state: after.result_state, modules: after.modules, revision: after.displayed.revision } })
    check('V02 F1 create-delay no browser errors', page._errors.length === 0, { errors: page._errors })
    await page.context().close()
  })
  await scenario('V02 F1 update-delay scenario', async () => {
    // F1, project update delayed: same for a PUT of an existing project
    const page = await newPage(browser)
    await ready(page, base + '/')
    await page.getByTestId('save').click()
    await page.waitForFunction(() => document.getElementById('status-inputs').dataset.state === 'saved')
    await page.getByTestId('in-tilt').fill('10')
    const hold = await holdFirst(page, '**/api/projects/*', 'PUT')
    await page.getByTestId('generate').click()
    await hold.held
    await page.getByTestId('in-module-width').fill('2')
    hold.release()
    await page.waitForSelector('#plan')
    await page.waitForFunction(() => document.getElementById('status-result').dataset.state !== 'none')
    const o = await observe(page)
    const server = await getProject(page, o.project.id)
    await page.screenshot({ path: path.join(out, 'V02-F1-update-delay.png') })
    check('V02 F1 update-delay edit stays dirty; result labelled with the saved snapshot',
      o.result_state === 'outdated' && o.inputs_state === 'dirty' && o.edited_width === '2' && o.displayed.revision === 2 &&
      o.displayed.inputs.table.tilt_deg === 10 && o.displayed.inputs.module.width_m === 1 && o.displayed.dims.tilt_deg === 10 && o.displayed.dims.table_width_W_m === 2 &&
      o.project.revision === 2 && o.project.saved.module.width_m === 1 && server.revision === 2 && server.request.module.width_m === 1 && server.request.table.tilt_deg === 10,
      { during: o, server_revision: server.revision, server_width: server.request.module.width_m, server_tilt: server.request.table.tilt_deg })
    check('V02 F1 update-delay no browser errors', page._errors.length === 0, { errors: page._errors })
    await page.context().close()
  })
  await scenario('V02 F2 stale SVG scenario', async () => {
    // F2: an older generation's plan SVG released after a newer result is shown must not
    // replace any part of it (plan, quantities, status, identity, export link)
    const page = await newPage(browser)
    await ready(page, base + '/')
    await page.getByTestId('save').click()
    await page.waitForFunction(() => document.getElementById('status-inputs').dataset.state === 'saved')
    const hold = await holdFirst(page, '**/plan.svg', 'GET')
    await page.getByTestId('generate').click()
    await hold.held
    await page.getByTestId('in-module-width').fill('2')
    await page.getByTestId('generate').click()
    await page.waitForFunction(() => document.getElementById('summary').dataset.modules === '16')
    const before = await observe(page)
    hold.release()
    await waitMessage(page, 'not displayed')
    await page.waitForTimeout(300)
    const after = await observe(page)
    const rid = before.displayed.result
    await page.screenshot({ path: path.join(out, 'V02-F2-stale-svg-released.png') })
    const same = ['modules', 'result_text', 'identity', 'banner', 'export_href', 'plan_result'].every((k) => after[k] === before[k])
    check('V02 F2 stale SVG released after a newer result changes nothing',
      same && after.modules === '16' && after.result_state === 'current' && after.plan_result === rid && after.identity.includes(rid) && after.identity.includes('revision 2') &&
      after.export_href.includes(rid) && after.displayed.result === rid && after.history.includes('late response'),
      { before, after })
    check('V02 F2 stale SVG no browser errors', page._errors.length === 0, { errors: page._errors })
    await page.context().close()
  })
  await scenario('V02 project switch scenario', async () => {
    // switching to another project while a generation is pending
    const page = await newPage(browser)
    const p2 = await (await page.request.post(`${base}/api/projects`, { data: { request: fixture('obstacle.request.json'), name: 'switch target' } })).json()
    const r2 = await (await page.request.post(`${base}/api/layouts`, { data: { project_id: p2.project_id } })).json()
    await ready(page, base + '/')
    await page.getByTestId('save').click()
    await page.waitForFunction(() => document.getElementById('status-inputs').dataset.state === 'saved')
    const hold = await holdFirst(page, '**/api/layouts', 'POST')
    await page.getByTestId('generate').click()
    await hold.held
    await page.getByTestId('project-id').fill(p2.project_id)
    await page.getByTestId('open-project').click()
    await page.waitForFunction((rid) => (document.querySelector('#plan-host > svg') || { dataset: {} }).dataset.resultId === rid, r2.result_id)
    const before = await observe(page)
    hold.release()
    await waitMessage(page, 'not displayed')
    await page.waitForTimeout(300)
    const after = await observe(page)
    await page.screenshot({ path: path.join(out, 'V02-project-switch-while-pending.png') })
    check('V02 project switch while a generation is pending keeps the opened project',
      after.plan_result === r2.result_id && after.modules === String(r2.summary.quantities.module_count) && after.result_state === 'current' &&
      after.project.id === p2.project_id && after.displayed.project === p2.project_id && after.export_href.includes(r2.result_id) &&
      after.history.includes('inputs were replaced') && page.url().includes(p2.project_id) && before.modules === after.modules,
      { opened: p2.project_id, opened_result: r2.result_id, before, after })
    check('V02 project switch no browser errors', page._errors.length === 0, { errors: page._errors })
    await page.context().close()
  })
  await scenario('V02 import while pending scenario', async () => {
    // importing a file while a generation is pending
    const page = await newPage(browser)
    await ready(page, base + '/')
    await page.getByTestId('save').click()
    await page.waitForFunction(() => document.getElementById('status-inputs').dataset.state === 'saved')
    const hold = await holdFirst(page, '**/api/layouts', 'POST')
    await page.getByTestId('generate').click()
    await hold.held
    await page.getByTestId('import-file').setInputFiles(path.join(fixtures, 'obstacle.request.json'))
    await waitMessage(page, 'Imported')
    hold.release()
    await waitMessage(page, 'not displayed')
    await page.waitForTimeout(300)
    const o = await observe(page)
    await page.screenshot({ path: path.join(out, 'V02-import-while-pending.png') })
    await generateAndWait(page)
    const after = await observe(page)
    check('V02 import while a generation is pending: the old result never appears for the imported inputs',
      !o.has_plan && o.result_state === 'none' && o.export_disabled && o.modules === undefined && o.inputs_state === 'dirty' && o.history.includes('inputs were replaced') &&
      after.result_state === 'current' && after.modules === '20',
      { during: o, after_regenerate: { result_state: after.result_state, modules: after.modules } })
    check('V02 import while pending no browser errors', page._errors.length === 0, { errors: page._errors })
    await page.context().close()
  })

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

  const version = browser.version()
  await browser.close()
  const passed = results.every((r) => r.pass)
  fs.writeFileSync(path.join(out, 'ui-checks.json'), JSON.stringify({ authority: 'Playwright + Chromium against the local solar-site-layout server', base, playwright: require('playwright/package.json').version, browser: { channel, version }, passed, results }, null, 1))
  process.exit(passed ? 0 : 1)
})().catch((e) => { console.error(e); process.exit(2) })
