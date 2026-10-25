// Solar Studio Module 01 browser client. All numbers come from the HTTP API; this file
// only edits the request, tracks revisions and displays immutable results.
'use strict';

const state = {
  request: null,        // the editor's request object
  project: null,        // {project_id, revision, savedJSON}
  genSeq: 0,            // increasing id of each generate press
  displayed: null,      // {seq, resultId, revision, inputsJSON, data}
  history: [],
  fullViewBox: null,
};

const $ = (id) => document.getElementById(id);

function canon(v) {
  if (Array.isArray(v)) return v.map(canon);
  if (v && typeof v === 'object') {
    const out = {};
    for (const k of Object.keys(v).sort()) out[k] = canon(v[k]);
    return out;
  }
  return v;
}
const editorJSON = () => JSON.stringify(canon(state.request));

function getPath(obj, path) {
  return path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj);
}
function setPath(obj, path, value) {
  const keys = path.split('.');
  let o = obj;
  for (const k of keys.slice(0, -1)) o = o[k];
  o[keys[keys.length - 1]] = value;
}

function message(html, cls = 'ok') {
  $('messages').innerHTML = `<div class="${cls}">${html}</div>`;
}
function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}
function showError(err) {
  const e = err.error || err;
  let txt = `${e.code}: ${e.message}` + (e.field ? `\nfield ${e.field}` : '');
  if (e.errors && e.errors.length > 1) txt += '\n' + e.errors.map((x) => `· ${x.code} ${x.field}: ${x.message}`).join('\n');
  message(esc(txt), 'err');
}

async function api(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: body !== undefined ? { 'content-type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  if (!res.ok) throw data;
  return data;
}

// ---- editor --------------------------------------------------------------------------
function populate() {
  const r = state.request;
  for (const el of document.querySelectorAll('[data-path]')) {
    const v = getPath(r, el.dataset.path);
    el.value = v === undefined ? '' : v;
  }
  $('boundary-json').value = JSON.stringify(r.boundary, null, 1);
  $('exclusions-json').value = JSON.stringify(r.exclusions, null, 1);
  const f = r.frame || {};
  $('frame-info').textContent = `Frame: ${f.kind} · ${f.id}${f.crs ? ' · ' + f.crs : ''} · units ${f.units} · x ${f.axes && f.axes.x}, y ${f.axes && f.axes.y}`;
  updateStatus();
}

function bindInputs() {
  for (const el of document.querySelectorAll('[data-path]')) {
    el.addEventListener('input', () => {
      let v = el.value;
      if (el.tagName !== 'SELECT') {
        v = el.value === '' ? null : Number(el.value);
        if (el.hasAttribute('data-int') && v !== null) v = Math.trunc(v);
      }
      setPath(state.request, el.dataset.path, v);
      updateStatus();
    });
  }
  for (const [id, key] of [['boundary-json', 'boundary'], ['exclusions-json', 'exclusions']]) {
    $(id).addEventListener('change', () => {
      try {
        state.request[key] = JSON.parse($(id).value);
        message(`${key} updated`);
      } catch (e) {
        message(esc(`${key} is not valid JSON: ${e.message}`), 'err');
      }
      updateStatus();
    });
  }
}

function isDirty() {
  return !state.project || editorJSON() !== state.project.savedJSON;
}

function resultIsCurrent() {
  const d = state.displayed;
  return !!(d && state.project && d.revision === state.project.revision && d.inputsJSON === editorJSON());
}

function updateStatus() {
  const si = $('status-inputs');
  if (!state.project) {
    si.textContent = 'Inputs: not saved';
    si.className = 'status dirty';
  } else if (isDirty()) {
    si.textContent = `Inputs: ${state.project.project_id} rev ${state.project.revision} + unsaved edits`;
    si.className = 'status dirty';
  } else {
    si.textContent = `Inputs: ${state.project.project_id} rev ${state.project.revision} (saved)`;
    si.className = 'status';
  }
  si.dataset.state = !state.project || isDirty() ? 'dirty' : 'saved';
  const sr = $('status-result');
  const d = state.displayed;
  if (!d) {
    sr.textContent = 'Result: none';
    sr.className = 'status';
    sr.dataset.state = 'none';
  } else {
    const cur = resultIsCurrent();
    sr.textContent = `Result ${d.resultId} from rev ${d.revision} — ${cur ? 'current' : 'outdated (historical: inputs changed since generation)'}`;
    sr.className = 'status ' + (cur ? 'current' : 'outdated');
    sr.dataset.state = cur ? 'current' : 'outdated';
    const banner = document.querySelector('#summary .banner');
    if (banner) {
      banner.className = 'banner ' + (cur ? 'current' : 'outdated');
      banner.textContent = cur
        ? `Current result for revision ${d.revision}`
        : `Historical result: generated from revision ${d.revision}; your inputs have changed since. Generate again for a current layout.`;
      banner.dataset.state = cur ? 'current' : 'outdated';
    }
  }
  if (state.project) $('project-id').value = state.project.project_id;
}

// ---- project ---------------------------------------------------------------------------
async function save() {
  const body = JSON.parse(editorJSON());
  let p;
  if (!state.project) {
    p = await api('POST', '/api/projects', { request: body, name: body.name });
  } else {
    p = await api('PUT', `/api/projects/${state.project.project_id}`, { expected_revision: state.project.revision, request: body });
  }
  state.project = { project_id: p.project_id, revision: p.revision, savedJSON: JSON.stringify(canon(body)) };
  const u = new URL(location.href);
  u.searchParams.set('project', p.project_id);
  history.replaceState(null, '', u);
  updateStatus();
  return p;
}

async function openProject(pid) {
  const p = await api('GET', `/api/projects/${encodeURIComponent(pid)}`);
  state.request = p.request;
  state.project = { project_id: p.project_id, revision: p.revision, savedJSON: JSON.stringify(canon(p.request)) };
  state.displayed = null;
  populate();
  if (p.selected_result_id) {
    const res = await api('GET', `/api/layouts/${p.selected_result_id}?project_id=${p.project_id}`);
    const seq = ++state.genSeq;
    await display({ seq, resultId: res.result_id, revision: p.selected_result_revision, inputsJSON: p.selected_result_is_current ? editorJSON() : '', data: res });
  }
  const u = new URL(location.href);
  u.searchParams.set('project', p.project_id);
  history.replaceState(null, '', u);
  message(`Opened ${esc(p.project_id)} at revision ${p.revision}`);
}

// ---- generation --------------------------------------------------------------------------
async function generate() {
  try {
    if (isDirty()) await save();
  } catch (e) {
    showError(e);
    return;
  }
  const seq = ++state.genSeq;
  const snapshot = editorJSON();
  const revision = state.project.revision;
  const projectId = state.project.project_id;
  $('generate').textContent = 'Generating…';
  $('generate').dataset.pending = String(Number($('generate').dataset.pending || 0) + 1);
  try {
    const res = await api('POST', '/api/layouts', { project_id: projectId, revision });
    const entry = { seq, resultId: res.result_id, revision, inputsJSON: snapshot, data: res };
    if (state.displayed && seq < state.displayed.seq) {
      state.history.push({ ...entry, note: 'late response from an older generation; not displayed' });
      renderHistory();
      message(`A late response for revision ${revision} arrived after a newer result; it was kept as historical and not displayed.`);
      return;
    }
    await display(entry);
    message(`Generated ${esc(res.result_id)} from revision ${revision} (${res.selection}).`);
  } catch (e) {
    showError(e);
  } finally {
    const n = Number($('generate').dataset.pending) - 1;
    $('generate').dataset.pending = String(n);
    if (n <= 0) $('generate').textContent = 'Generate layout';
  }
}

async function display(entry) {
  state.displayed = entry;
  state.history.push(entry);
  const svgText = await (await fetch(`/api/layouts/${entry.resultId}/plan.svg`)).text();
  const host = $('plan-host');
  host.innerHTML = svgText.replace(/<\?xml[^>]*>/, '');
  const page = host.querySelector('svg');
  page.classList.add('page');
  page.removeAttribute('width');
  page.removeAttribute('height');
  const plan = page.querySelector('#plan');
  state.fullViewBox = plan.getAttribute('data-full-viewbox').split(' ').map(Number);
  for (const cb of document.querySelectorAll('[data-layer]')) applyLayer(cb);
  renderSummary(entry);
  renderHistory();
  const fmt = $('export-format').value;
  const a = $('export-link');
  a.href = `/api/layouts/${entry.resultId}/exports/${fmt}`;
  a.classList.remove('disabled');
  a.removeAttribute('aria-disabled');
  updateStatus();
}

function kv(label, value) {
  return `<div class="kv"><span>${esc(label)}</span><b>${esc(value)}</b></div>`;
}
const f3 = (x) => (x === null || x === undefined ? 'n/a (zero denominator)' : Number(x).toFixed(3));

function renderSummary(entry) {
  const s = entry.data.summary;
  const q = s.quantities;
  const d = s.dimensions;
  const p = s.placement;
  let html = '<div class="banner"></div>';
  html += kv('Tables', q.table_count) + kv('Modules', q.module_count) + kv('DC capacity (kWp)', q.dc_capacity_kwp.toFixed(3));
  html += kv('Table W × L (m)', `${d.table_width_W_m.toFixed(3)} × ${d.table_slope_length_L_m.toFixed(3)}`);
  html += kv('Depth D / rise H (m)', `${d.table_projected_depth_D_m.toFixed(3)} / ${d.table_rise_H_m.toFixed(3)}`);
  html += kv('Row pitch / clear gap (m)', `${p.row_pitch_m} / ${p.clear_row_gap_m.toFixed(3)}`);
  html += kv('Gross site area (m²)', q.gross_site_area_m2.toFixed(2)) + kv('Buildable area (m²)', q.buildable_area_m2.toFixed(2));
  html += kv('Module area phys/proj (m²)', `${q.physical_module_area_m2.toFixed(2)} / ${q.projected_module_area_m2.toFixed(2)}`);
  html += kv('Coverage gross', f3(q.module_ground_coverage_gross)) + kv('Coverage buildable', f3(q.module_ground_coverage_buildable));
  html += kv('Placement', `${p.mode} · ${p.optimality}`) + kv('Selected phase', p.selected_phase_index.join(','));
  html += kv('Verified', entry.data.verification.ok ? 'yes (independent verifier)' : 'NO');
  html += `<div class="wide" data-testid="identity">Result <code>${esc(entry.resultId)}</code> · revision ${entry.revision} · input ${esc(s.input_digest.slice(0, 16))}… · payload ${esc(entry.data.payload_digest.slice(0, 16))}… · frame ${esc(s.frame.kind)} ${esc(s.frame.id)} · z ${esc(s.z_kind)}</div>`;
  if (s.warnings.length) html += `<div class="wide">Warnings: ${s.warnings.map(esc).join(' · ')}</div>`;
  html += '<div class="wide">Preliminary layout under stated assumptions: flat site, synthetic relative heights, user-supplied pitch, bounded lattice search. No energy, electrical or structural outputs.</div>';
  $('summary').innerHTML = html;
  $('summary').dataset.modules = q.module_count;
  $('summary').dataset.tables = q.table_count;
}

function renderHistory() {
  const items = state.history
    .slice(-8)
    .reverse()
    .map((h) => `<li class="${h.note ? 'superseded' : ''}" data-result="${esc(h.resultId)}">#${h.seq} ${esc(h.resultId)} · rev ${h.revision} · ${h.data.summary.quantities.module_count} modules${h.note ? ' · ' + esc(h.note) : ''}</li>`)
    .join('');
  $('history').innerHTML = `<details><summary>Results this session (${state.history.length})</summary><ul>${items}</ul></details>`;
}

// ---- plan viewer -------------------------------------------------------------------------
function planEl() {
  return $('plan-host').querySelector('#plan');
}
function setViewBox(vb) {
  const plan = planEl();
  if (!plan) return;
  plan.setAttribute('viewBox', vb.map((v) => +v.toFixed(6)).join(' '));
  const z = state.fullViewBox[2] / vb[2];
  const st = $('plan-host').querySelector('#scale-text');
  const bar = $('plan-host').querySelector('#scale-bar');
  if (st && bar) {
    const base = Number(st.getAttribute('data-scale'));
    st.textContent = z === 1 ? `Scale 1:${base} (page in mm, plan in metres)` : `Scale 1:${Math.round(base / z)} at this zoom (plan in metres)`;
    const m = Number(bar.getAttribute('data-bar-m')) / z;
    $('plan-host').querySelector('#scale-bar-label').textContent = `${+m.toPrecision(4)} m`;
  }
}
function currentViewBox() {
  return planEl().getAttribute('viewBox').split(' ').map(Number);
}
function zoom(factor, cx, cy) {
  if (!planEl()) return;
  const [x, y, w, h] = currentViewBox();
  const px = cx === undefined ? x + w / 2 : cx;
  const py = cy === undefined ? y + h / 2 : cy;
  const nw = w / factor;
  const nh = h / factor;
  setViewBox([px - (px - x) / factor, py - (py - y) / factor, nw, nh]);
}
function applyLayer(cb) {
  const g = $('plan-host').querySelector('#' + cb.dataset.layer);
  if (g) g.style.display = cb.checked ? '' : 'none';
}
function bindViewer() {
  $('fit').onclick = () => state.fullViewBox && setViewBox(state.fullViewBox.slice());
  $('zoom-in').onclick = () => zoom(2);
  $('zoom-out').onclick = () => zoom(0.5);
  for (const cb of document.querySelectorAll('[data-layer]')) cb.addEventListener('change', () => applyLayer(cb));
  const host = $('plan-host');
  host.addEventListener('wheel', (ev) => {
    const plan = planEl();
    if (!plan) return;
    ev.preventDefault();
    const r = plan.getBoundingClientRect();
    const [x, y, w, h] = currentViewBox();
    const s = Math.max(w / r.width, h / r.height);
    const cx = x + (ev.clientX - r.left - (r.width - w / s) / 2) * s;
    const cy = y + (ev.clientY - r.top - (r.height - h / s) / 2) * s;
    zoom(ev.deltaY < 0 ? 1.25 : 0.8, cx, cy);
  }, { passive: false });
  let drag = null;
  host.addEventListener('pointerdown', (ev) => { if (planEl()) drag = { x: ev.clientX, y: ev.clientY, vb: currentViewBox() }; });
  window.addEventListener('pointerup', () => { drag = null; });
  window.addEventListener('pointermove', (ev) => {
    if (!drag) return;
    const r = planEl().getBoundingClientRect();
    const s = Math.max(drag.vb[2] / r.width, drag.vb[3] / r.height);
    setViewBox([drag.vb[0] - (ev.clientX - drag.x) * s, drag.vb[1] - (ev.clientY - drag.y) * s, drag.vb[2], drag.vb[3]]);
  });
  $('export-format').addEventListener('change', () => {
    if (state.displayed) $('export-link').href = `/api/layouts/${state.displayed.resultId}/exports/${$('export-format').value}`;
  });
}

// ---- other actions ---------------------------------------------------------------------
async function validate() {
  try {
    const v = await api('POST', '/api/validate', JSON.parse(editorJSON()));
    if (!v.valid) return showError(v.error);
    const d = v.dimensions;
    message(`Valid. W ${d.table_width_W_m.toFixed(3)} m, L ${d.table_slope_length_L_m.toFixed(3)} m, D ${d.table_projected_depth_D_m.toFixed(3)} m, H ${d.table_rise_H_m.toFixed(3)} m, clear gap ${d.clear_row_gap_m.toFixed(3)} m; ≤ ${v.candidate_bounds.candidates_total_upper_bound} candidates.`);
    return v;
  } catch (e) {
    showError(e);
  }
}

async function pitch() {
  try {
    const v = await api('POST', '/api/validate', JSON.parse(editorJSON()));
    if (!v.valid) return showError(v.error);
    const r = state.request;
    const out = await api('POST', '/api/row-pitch', {
      schema_version: 'solar.row_pitch.request/1',
      table_slope_length_m: v.dimensions.table_slope_length_L_m,
      tilt_deg: r.table.tilt_deg,
      solar_elevation_deg: Number($('pitch-elevation').value),
      minimum_clear_row_gap_m: r.placement.minimum_clear_row_gap_m,
      model: 'flat_equal_height_infinite_rows_perpendicular_front_sun',
    });
    $('pitch-out').textContent = `${out.label}: D ${out.projected_depth_m.toFixed(3)} m, H ${out.table_rise_m.toFixed(3)} m, shadow gap ${out.shadow_clear_gap_m.toFixed(3)} m → recommended pitch ${out.recommended_pitch_m.toFixed(3)} m (${out.governed_by}).\nAssumes ${out.assumptions.join('; ')}. Not provided: ${out.not_provided.join('; ')}.`;
  } catch (e) {
    $('pitch-out').textContent = '';
    showError(e);
  }
}

async function loadExample(name) {
  state.request = await (await fetch(`/static/examples/${name}.json`)).json();
  populate();
  message(`Loaded example ${esc(name)} (unsaved)`);
}

function bindActions() {
  $('load-example').onclick = () => loadExample($('example').value);
  $('validate').onclick = validate;
  $('save').onclick = async () => {
    try {
      const p = await save();
      message(`Saved ${esc(p.project_id)} revision ${p.revision}`);
    } catch (e) {
      showError(e);
    }
  };
  $('generate').onclick = generate;
  $('open-project').onclick = async () => {
    try {
      await openProject($('project-id').value.trim());
    } catch (e) {
      showError(e);
    }
  };
  $('pitch-calc').onclick = pitch;
  $('import-file').addEventListener('change', async (ev) => {
    const file = ev.target.files[0];
    if (!file) return;
    try {
      state.request = JSON.parse(await file.text());
      populate();
      message(`Imported ${esc(file.name)} (unsaved)`);
    } catch (e) {
      message(esc(`Import failed: ${e.message}`), 'err');
    }
  });
}

(async function init() {
  bindInputs();
  bindViewer();
  bindActions();
  const pid = new URL(location.href).searchParams.get('project');
  if (pid) {
    try {
      await openProject(pid);
      return;
    } catch (e) {
      showError(e);
    }
  }
  await loadExample('rectangle');
  document.body.dataset.ready = '1';
})().finally(() => { document.body.dataset.ready = '1'; });
