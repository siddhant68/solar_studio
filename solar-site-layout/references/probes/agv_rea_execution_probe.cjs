// REA execution-coverage probe of the built reference (R02/R05 support).
//
// Launches the offline Chromium with a loopback CDP port, opens the reference's
// "Adjust the panels by hand" fold, then runs `rea observe-web-execution` twice against
// the same page target: an idle window, and a window during which this script changes
// the row-pitch control (control-array-pitch) and the tilt control. REA performs the
// coverage capture; Playwright only performs the user action during REA's window.
//
//   node agv_rea_execution_probe.cjs BASE_URL OUT_DIR REA_DIR NODE_BIN_DIR
'use strict'
const fs = require('fs')
const path = require('path')
const { spawn } = require('child_process')
const { chromium } = require('playwright')

const [base, out, reaDir, nodeBin] = process.argv.slice(2)
fs.mkdirSync(out, { recursive: true })
const PORT = 9333
const env = { ...process.env, PATH: `${nodeBin}:${process.env.PATH}` }

function rea(args, file, onArmed) {
  return new Promise((resolve) => {
    const p = spawn('npx', ['--no-install', 'rea', ...args, '--format', 'json'], { cwd: reaDir, env })
    const chunks = []
    const errs = []
    let armed = false
    p.stdout.on('data', (d) => chunks.push(d))
    p.stderr.on('data', (d) => {
      errs.push(d)
      // REA prints a progress record when its observation window is armed; act only then
      if (!armed && onArmed && Buffer.concat(errs).toString().includes('observation armed')) {
        armed = true
        onArmed()
      }
    })
    p.on('close', (code) => {
      fs.writeFileSync(path.join(out, file), Buffer.concat(chunks))
      fs.writeFileSync(path.join(out, file + '.stderr'), Buffer.concat(errs))
      resolve({ code, file })
    })
  })
}

;(async () => {
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome', args: [`--remote-debugging-port=${PORT}`, '--proxy-server=http://127.0.0.1:9'] })
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 } })
  const page = await ctx.newPage()
  await page.goto(base, { waitUntil: 'load' })
  await page.getByTestId('app-root').waitFor({ state: 'visible' })
  await page.waitForTimeout(5000)
  await page.getByTestId('action-step-panels').click()
  const fold = page.getByTestId('details-panels-by-hand')
  if ((await fold.getAttribute('open')) === null) await fold.locator('summary').first().click()
  await page.getByTestId('control-array-pitch').waitFor({ state: 'visible' })
  await page.waitForTimeout(1500)
  const targets = await rea(['list-browser-targets', `http://127.0.0.1:${PORT}`], 'list-browser-targets.json')
  const list = JSON.parse(fs.readFileSync(path.join(out, targets.file)))
  const flat = JSON.stringify(list)
  const m = flat.match(/"target_id":"([^"]+)"[^}]*?"url":"http:\/\/127\.0\.0\.1:4173\//) || flat.match(/"(?:target_id|targetId|id)":"([0-9A-F]{32})"/)
  if (!m) throw new Error('no page target found in REA list-browser-targets output')
  const targetId = m[1]
  const record = { base, cdp_port: PORT, target_id: targetId, windows: [] }
  // idle window
  const idle = await rea(['observe-web-execution', `http://127.0.0.1:${PORT}`, targetId, '--observation-ms', '6000', '--allowed-origins', 'http://127.0.0.1:4173'], 'observe-idle.json')
  record.windows.push({ name: 'idle', exit: idle.code, file: idle.file })
  // action window: REA observes; this script changes row pitch then tilt inside the window
  let armedResolve
  const armedSignal = new Promise((r) => { armedResolve = r })
  const action = rea(['observe-web-execution', `http://127.0.0.1:${PORT}`, targetId, '--observation-ms', '8000', '--allowed-origins', 'http://127.0.0.1:4173'], 'observe-pitch-change.json', () => armedResolve(Date.now()))
  const armedAt = await armedSignal
  await page.waitForTimeout(300)
  const before = await page.getByTestId('readout-array-gcr').textContent()
  const actedAt = Date.now()
  await page.getByTestId('control-array-pitch').fill('6')
  await page.waitForTimeout(800)
  await page.getByTestId('control-array-tilt').fill('35')
  const after = await page.getByTestId('readout-array-gcr').textContent()
  const finishedAt = Date.now()
  const a = await action
  record.windows.push({ name: 'pitch_and_tilt_change', exit: a.code, file: a.file, gcr_before: before, gcr_after: after, armed_ms: armedAt, action_started_ms: actedAt, action_finished_ms: finishedAt })
  fs.writeFileSync(path.join(out, 'execution-probe.json'), JSON.stringify(record, null, 1))
  await browser.close()
  console.log(JSON.stringify(record))
})().catch((e) => { console.error(e); process.exit(1) })
