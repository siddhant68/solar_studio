const { chromium } = require('playwright')
;(async () => {
  const b = await chromium.launch({ channel: process.env.CH || undefined }); const p = await b.newPage()
  const bad = []; const cons = []
  p.on('response', r => { if (r.status() >= 400) bad.push({ status: r.status(), url: r.url(), type: r.request().resourceType() }) })
  p.on('requestfailed', r => bad.push({ failed: r.failure() && r.failure().errorText, url: r.url() }))
  p.on('console', m => { if (m.type() === 'error') cons.push({ text: m.text(), location: m.location() }) })
  await p.goto(process.argv[2]); await p.waitForSelector('body[data-ready="1"]')
  await p.getByTestId('generate').click(); await p.waitForSelector('#plan')
  await p.reload(); await p.waitForSelector('body[data-ready="1"]'); await p.waitForTimeout(1000)
  console.log(JSON.stringify({ bad, cons }, null, 1)); await b.close()
})()
