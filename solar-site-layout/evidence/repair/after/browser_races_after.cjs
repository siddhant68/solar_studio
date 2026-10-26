// Copy of reviews/module-01/2026-10-26/browser_races.cjs for the post-repair observation.
// Only change: after releasing the held SVG it waits for the "not displayed" notice instead
// of for the buggy 24-module state, which the repaired client never reaches.
const fs=require('fs');
const {chromium}=require(process.env.SOLAR_REVIEW_PLAYWRIGHT || '/Users/sidhandsome/solar-reviews/2026-10-26/browser-tools/node_modules/playwright');
const out=process.env.SOLAR_REVIEW_OUT || __dirname;const base=process.env.SOLAR_REVIEW_BASE || 'http://127.0.0.1:18765';
(async()=>{
 const browser=await chromium.launch({channel:process.env.SOLAR_REVIEW_CHANNEL || 'chrome',headless:true});const results={browser_version:browser.version()};
 try{
  const page=await browser.newPage({viewport:{width:1500,height:950}});await page.goto(base);await page.waitForSelector('body[data-ready="1"]');
  let release,heldResolve;const gate=new Promise(r=>release=r);const held=new Promise(r=>heldResolve=r);
  await page.route('**/api/projects',async route=>{if(route.request().method()!=='POST')return route.continue();const response=await route.fetch();heldResolve();await gate;await route.fulfill({response});});
  await page.getByTestId('generate').click();await held;await page.getByTestId('in-module-width').fill('2');release();
  await page.waitForSelector('#plan');await page.waitForFunction(()=>document.querySelector('#summary').dataset.modules);
  results.edit_during_autosave=await page.evaluate(()=>({edited_width:document.querySelector('[data-testid=in-module-width]').value,inputs_state:document.querySelector('#status-inputs').dataset.state,result_state:document.querySelector('#status-result').dataset.state,displayed_modules:Number(document.querySelector('#summary').dataset.modules),displayed_table_width:state.displayed.data.summary.dimensions.table_width_W_m,snapshot_claimed_width:JSON.parse(state.displayed.inputsJSON).module.width_m,saved_input_width:JSON.parse(state.project.savedJSON).module.width_m,revision:state.displayed.revision}));
  await page.screenshot({path:out+'/race-autosave.png'});await page.close();
  const p=await browser.newPage({viewport:{width:1500,height:950}});await p.goto(base);await p.waitForSelector('body[data-ready="1"]');await p.getByTestId('save').click();await p.waitForFunction(()=>document.querySelector('#status-inputs').dataset.state==='saved');
  let releaseSvg,heldSvgResolve;const svgGate=new Promise(r=>releaseSvg=r);const heldSvg=new Promise(r=>heldSvgResolve=r);let count=0;
  await p.route('**/plan.svg',async route=>{if(++count>1)return route.continue();const response=await route.fetch();heldSvgResolve();await svgGate;await route.fulfill({response});});
  await p.getByTestId('generate').click();await heldSvg;await p.getByTestId('in-module-width').fill('2');await p.getByTestId('generate').click();await p.waitForFunction(()=>document.querySelector('#summary').dataset.modules==='16');
  results.delayed_svg_before_release=await p.evaluate(()=>({modules:document.querySelector('#summary').dataset.modules,status:document.querySelector('#status-result').textContent,export:document.querySelector('#export-link').getAttribute('href'),state_result:state.displayed.resultId}));
  releaseSvg();await p.waitForFunction(()=>document.getElementById('messages').textContent.includes('not displayed'),null,{timeout:30000});await p.waitForTimeout(500);
  results.delayed_svg_after_release=await p.evaluate(()=>({modules:document.querySelector('#summary').dataset.modules,status:document.querySelector('#status-result').textContent,summary_identity:document.querySelector('[data-testid=identity]').textContent,banner:document.querySelector('#summary .banner').textContent,export:document.querySelector('#export-link').getAttribute('href'),state_result:state.displayed.resultId,current_revision:state.project.revision,edited_width:document.querySelector('[data-testid=in-module-width]').value}));
  await p.screenshot({path:out+'/race-delayed-svg.png'});await p.close();
 }finally{await browser.close();}
 fs.writeFileSync(out+'/browser-races.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results,null,2));
})().catch(e=>{console.error(e);process.exit(1)});
