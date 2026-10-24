'use strict';
const $ = id => document.getElementById(id);
const STACK_LABELS = {sky130: 'SKY130', soi_al: 'SOI + Al'};
const sampleLabel = name => t(`sample.${name}`);
let stack = null, upload = null, sample = 'zundamon', selectedResult = 'sample-sky130_zundamon', result = null;
let activeJob = null, pollTimer = null, zoom = 1, imageMode = 'prediction', yamlDirty = false, previewURL = null;
let resultGeneration = 0, yamlStatus = 'yaml.idle';
const api = async (url, options = {}) => {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message; try { const body = await response.json(); message = body.detail || body; } catch { message = response.statusText; }
    throw new Error(typeof message === 'string' ? localizeServerMessage(message) : JSON.stringify(message));
  }
  return response;
};
function setYamlStatus(key) { yamlStatus = key; $('yaml-status').textContent = t(key); }
function showError(error) { $('error').textContent = error.message || String(error); $('error').hidden = false; }
function clearError() { $('error').hidden = true; }
function artifact(name, download = false) { return `/api/jobs/${selectedResult}/files/${name}${download ? '?download=true' : ''}`; }
function updateSize() { const width = Number($('pixel-size').value) * Number($('columns').value); $('layout-width').textContent = `${width.toLocaleString('en-US', {maximumFractionDigits: 3})} µm`; }
function renderStack() {
  $('stack-layers').replaceChildren();
  stack.layers.forEach((layer, i) => {
    const row = document.createElement('div'); row.className = 'stack-row' + (layer.patterned ? ' patterned' : '') + (i === stack.layers.length-1 ? ' substrate' : '');
    const material = document.createElement('span'); material.className = 'material'; material.textContent = layer.material;
    if (layer.patterned) { const badge = document.createElement('span'); badge.className = 'pattern-label'; badge.textContent = t('stack.grating'); material.append(badge); }
    row.append(material);
    if (i === 0 || i === stack.layers.length - 1) { const text = document.createElement('span'); text.className = 'half-space'; text.textContent = t('stack.halfSpace'); row.append(text); }
    else {
      const field = document.createElement('input'); field.type = 'number'; field.value = layer.thickness_um; field.step = 'any'; field.min = '0.000001'; field.required = true; field.setAttribute('aria-label', t('stack.thicknessLabel', i, layer.material));
      field.addEventListener('input', () => { layer.thickness_um = Number(field.value); $('stack-yaml').value = JSON.stringify(stack, null, 2); yamlDirty = false; setYamlStatus('yaml.edited'); }); row.append(field);
    }
    $('stack-layers').append(row);
  });
}
async function loadPresets() {
  const data = await (await api('/api/presets')).json();
  if (!data.presets.length) throw new Error(t('error.noPresets'));
  const labels = {sky130: 'SKY130 — Met1', soi_al: 'SOI + Al'};
  $('preset').replaceChildren(...data.presets.map(p => new Option(labels[p.id] || p.name, p.id)));
  $('preset').value = data.presets.some(p => p.id === 'sky130') ? 'sky130' : data.presets[0].id;
  await loadPreset($('preset').value);
}
async function loadPreset(name) {
  const data = await (await api(`/api/presets/${name}`)).json(); stack = data.stack;
  $('stack-yaml').value = data.yaml; yamlDirty = false;
  $('gds-layer').value = stack.gds.layer; $('gds-layer').disabled = !!stack.gds.fixed_layer;
  $('min-width').value = stack.rules.min_width_um; $('min-space').value = stack.rules.min_space_um;
  setYamlStatus('yaml.idle'); renderStack();
}
async function applyYaml() {
  const data = await (await api('/api/stack/validate', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({yaml: $('stack-yaml').value})})).json();
  stack = data.stack; $('stack-yaml').value = data.yaml; yamlDirty = false;
  $('gds-layer').disabled = !!stack.gds.fixed_layer; if (stack.gds.fixed_layer) $('gds-layer').value = stack.gds.layer;
  setYamlStatus('yaml.applied'); renderStack();
}
async function selectFile(file) {
  if (!file) return;
  clearError();
  if (file.size > 16 * 1024 * 1024) throw new Error(localizeServerMessage('Images must be 16 MB or smaller.'));
  const data = new FormData(); data.set('image', file);
  const blob = await (await api('/api/preview', {method: 'POST', body: data})).blob();
  upload = file; if (previewURL) URL.revokeObjectURL(previewURL); previewURL = URL.createObjectURL(blob);
  $('source-preview').src = previewURL; $('file-label').textContent = file.name;
}
function displayImage() {
  $('show-prediction').classList.toggle('selected', imageMode === 'prediction'); $('show-input').classList.toggle('selected', imageMode === 'input');
  $('appearance').src = artifact(imageMode === 'prediction' ? 'appearance_large.png' : 'input_white.png');
  $('appearance').alt = t(imageMode === 'prediction' ? 'image.altPrediction' : 'image.altInput');
  zoom = 1; applyZoom();
}
function applyZoom() {
  const stage = $('image-stage'), img = $('appearance'); stage.classList.toggle('zoomed', zoom > 1);
  img.style.width = zoom > 1 ? `${stage.clientWidth * zoom}px` : ''; img.style.height = 'auto';
  if (zoom === 1) { stage.scrollLeft = 0; stage.scrollTop = 0; }
  $('zoom-fit').textContent = zoom === 1 ? t('image.fit') : `${Math.round(zoom * 100)}%`;
}
async function loadResult(id) {
  const generation = ++resultGeneration;
  const data = await (await api(`/api/jobs/${id}`)).json();
  if (generation !== resultGeneration) return;
  if (data.status !== 'complete') throw new Error(t('result.notReady'));
  selectedResult = id; result = data; localStorage.setItem('color2gds-result', id);
  const s = data.summary, m = data.manifest;
  const [, sampleStack, sampleName] = id.match(/^sample-(sky130|soi_al)_(\w+)$/) || [];
  const label = sampleStack ? t('result.saved', sampleLabel(sampleName), STACK_LABELS[sampleStack]) : t('result.compiled', data.label);
  $('result-title').textContent = label; $('result-title').title = `${label} / ${s.stack}`; $('result-tag').textContent = id.startsWith('sample-') ? 'SAMPLE' : 'COMPILED';
  if (![...$('result-select').options].some(o => o.value === id)) { const o = new Option(label, id); $('result-select').append(o); }
  labelSampleOptions();
  $('result-select').value = id;
  const viewer = `/viewer/?url=${encodeURIComponent(new URL(artifact('image.gds'), location.origin).href)}&tools=move,select,ruler,fit-all,theme&drop=false&layers=true`;
  $('gds-viewer').src = viewer; $('open-viewer').href = viewer;
  $('gds-meta').textContent = `Layer ${m.gds_layer} / ${m.gds_datatype}`;
  $('download-gds').href = artifact('image.gds', true); $('download-image').href = artifact('appearance.png', true);
  $('download-npz').href = artifact('appearance.npz', true); $('download-manifest').href = artifact('manifest.json', true); $('download-bmp').href = artifact('image.bmp', true); $('open-report').href = artifact('report.html');
  $('download-palette').href = `${artifact('palette.png', true)}&lang=${lang}`;
  $('download-palette-npz').href = artifact('palette.npz', true);
  $('palette-caption').textContent = `${m.stack.name} · ${label}`;
  $('image-caption').textContent = t('image.caption', m.settings.theta, m.settings.modes);
  $('metric-size').textContent = `${s.canvas_um.map(x => Number(x.toFixed(2))).join(' × ')} µm`;
  $('metric-grid').textContent = s.pixel_grid.join(' × '); $('metric-error').textContent = s.mean_deltaE00_source.toFixed(2);
  $('metric-check').textContent = t(s.closed_loop_max_Lab_difference <= 1e-7 ? 'metric.match' : 'metric.review'); $('metric-check').className = 'match';
  $('assumptions').replaceChildren(); for (const text of s.assumptions || []) { const li = document.createElement('li'); li.textContent = text; $('assumptions').append(li); }
  displayImage();
  loadPalette(id, generation, m);
}
async function refreshHistory() {
  const {jobs} = await (await api('/api/jobs')).json();
  for (const job of jobs) if (job.status === 'complete' && ![...$('result-select').options].some(o => o.value === job.id)) {
    const label = `${new Date(job.created * 1000).toLocaleTimeString(lang === 'ja' ? 'ja-JP' : 'en-US', {hour:'2-digit', minute:'2-digit'})} · ${job.label}`;
    $('result-select').append(new Option(label, job.id));
  }
}
function busy(value) { $('compile').disabled = value; $('job-status').hidden = !value; $('result-dot').classList.toggle('busy', value); }
async function poll() {
  if (!activeJob) return;
  try {
    const job = await (await api(`/api/jobs/${activeJob}`)).json();
    if (['complete','failed','cancelled','interrupted'].includes(job.status)) {
      activeJob = null; localStorage.removeItem('color2gds-job'); busy(false);
      if (job.status === 'complete') { await refreshHistory(); await loadResult(job.id); }
      else showError(new Error(job.status === 'cancelled' ? t('job.cancelled') : job.error ? localizeServerMessage(job.error) : t('job.failed')));
      return;
    }
    const elapsed = job.started ? Math.floor(Date.now()/1000-job.started) : 0;
    const refined = /round 0:/.test(job.log || '');
    $('job-message').textContent = job.status === 'queued' ? t('job.queued') : t(refined ? 'job.refining' : 'job.computing', elapsed);
    $('job-description').textContent = t('job.running');
    $('job-log').textContent = job.log || t('job.preparing');
    pollTimer = setTimeout(poll, 1500);
  } catch (e) { showError(e); $('job-message').textContent = t('job.reconnecting'); pollTimer = setTimeout(poll, 5000); }
}
$('compile-form').addEventListener('submit', async event => {
  event.preventDefault(); clearError(); $('compile').disabled = true;
  try {
    if (yamlDirty) await applyYaml();
    const quality = {standard: [31,1], preview: [11,5], fine: [51,.5]}[$('quality').value];
    const options = {min_width_um: Number($('min-width').value), min_space_um: Number($('min-space').value), pixel_size_um: Number($('pixel-size').value), columns: Number($('columns').value), gds_layer: Number($('gds-layer').value), angle_deg: Number($('angle').value), modes: quality[0], step_nm: quality[1], refine_rounds: Number($('rounds').value), mapping: $('mapping').value};
    const data = new FormData(); data.set('options', JSON.stringify(options)); data.set('stack', JSON.stringify(stack));
    if (upload) data.set('image', upload); else data.set('sample', sample);
    const job = await (await api('/api/jobs', {method: 'POST', body: data})).json();
    activeJob = job.id; localStorage.setItem('color2gds-job', activeJob); busy(true); $('job-message').textContent = t('job.starting'); $('job-status').scrollIntoView({behavior:'smooth', block:'nearest'}); poll();
  } catch (e) { showError(e); $('compile').disabled = false; }
});
$('cancel').addEventListener('click', async () => { if (!activeJob) return; try { await api(`/api/jobs/${activeJob}/cancel`, {method:'POST'}); } catch (e) { showError(e); } });
$('preset').addEventListener('change', () => loadPreset($('preset').value).catch(showError));
$('stack-yaml').addEventListener('input', () => { yamlDirty = true; setYamlStatus('yaml.dirty'); });
$('apply-yaml').addEventListener('click', () => { clearError(); applyYaml().catch(showError); });
$('image-file').addEventListener('change', event => selectFile(event.target.files[0]).catch(showError));
for (const button of document.querySelectorAll('[data-sample]')) button.addEventListener('click', () => { upload = null; sample = button.dataset.sample; $('image-file').value = ''; $('source-preview').src = `/api/jobs/sample-sky130_${sample}/files/input.png`; $('file-label').textContent = sampleLabel(sample); });
for (const event of ['dragenter','dragover']) $('drop-zone').addEventListener(event, e => { e.preventDefault(); $('drop-zone').classList.add('dragover'); });
for (const event of ['dragleave','drop']) $('drop-zone').addEventListener(event, e => { e.preventDefault(); $('drop-zone').classList.remove('dragover'); });
$('drop-zone').addEventListener('drop', e => selectFile(e.dataTransfer.files[0]).catch(showError));
for (const id of ['pixel-size','columns']) $(id).addEventListener('input', updateSize);
$('result-select').addEventListener('change', () => loadResult($('result-select').value).catch(showError));
$('show-prediction').addEventListener('click', () => { imageMode = 'prediction'; displayImage(); });
$('show-input').addEventListener('click', () => { imageMode = 'input'; displayImage(); });
$('zoom-in').addEventListener('click', () => { zoom = Math.min(8, zoom * 1.5); applyZoom(); });
$('zoom-out').addEventListener('click', () => { zoom = Math.max(1, zoom / 1.5); applyZoom(); });
$('zoom-fit').addEventListener('click', () => { zoom = 1; applyZoom(); });
window.addEventListener('resize', applyZoom);
function labelSampleOptions() {
  for (const option of $('result-select').options) {
    const [, sampleStack, sampleName] = option.value.match(/^sample-(sky130|soi_al)_(\w+)$/) || [];
    if (sampleStack) option.textContent = t('result.option', sampleLabel(sampleName), STACK_LABELS[sampleStack]);
  }
}
function applyLanguage() {
  translatePage(); labelSampleOptions(); setYamlStatus(yamlStatus); applyZoom();
  if (!upload) $('file-label').textContent = sampleLabel(sample);
  if (!activeJob) { $('job-message').textContent = t('job.queued'); $('job-description').textContent = t('job.idle'); }
  if (!result) $('image-caption').textContent = t('image.captionDefault');
  if (stack) renderStack();
}
$('lang-toggle').addEventListener('click', () => {
  lang = lang === 'ja' ? 'en' : 'ja';
  try { localStorage.setItem('color2gds-lang', lang); } catch {}
  applyLanguage();
  if (result) loadResult(selectedResult).catch(showError);
});
(async () => {
  applyLanguage();
  try {
    await loadPresets(); await refreshHistory();
    const saved = localStorage.getItem('color2gds-result');
    try { await loadResult(saved || 'sample-sky130_zundamon'); } catch { await loadResult('sample-sky130_zundamon'); }
    activeJob = localStorage.getItem('color2gds-job'); if (activeJob) { busy(true); poll(); }
  } catch (e) { showError(e); }
})();
