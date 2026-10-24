'use strict';

let currentSpectrum = null, spectrumDownloadURL = null;

function clearSpectrumDownload() {
  if (spectrumDownloadURL) URL.revokeObjectURL(spectrumDownloadURL);
  spectrumDownloadURL = null;
  $('download-spectrum-csv').removeAttribute('href');
}

function updateSpectrumDownload(id, index, wavelengths, entry) {
  clearSpectrumDownload();
  const rows = ['wavelength_nm,reflectance_percent',
    ...wavelengths.map((wavelength, i) => `${wavelength},${entry.reflectance[i] * 100}`)];
  // UTF-8 BOM and CRLF allow spreadsheet applications to open the CSV directly.
  const csv = new Blob(['\uFEFF', rows.join('\r\n'), '\r\n'], {type: 'text/csv;charset=utf-8'});
  spectrumDownloadURL = URL.createObjectURL(csv);
  const link = $('download-spectrum-csv');
  const candidate = entry.pitch_nm === null ? 'blank' : `candidate-${String(index + 1).padStart(2, '0')}`;
  link.href = spectrumDownloadURL;
  link.download = `spectrum_${id}_${candidate}.csv`;
  link.setAttribute('aria-label', t('spectrum.csvLabel', entry.label));
}
window.addEventListener('resize', () => {
  if (currentSpectrum && !$('spectrum-detail').hidden) renderSpectrum(...currentSpectrum);
});

async function loadPalette(id, generation, manifest) {
  const status = $('palette-status'), swatches = $('palette-swatches');
  clearSpectrumDownload();
  swatches.replaceChildren();
  $('spectrum-detail').hidden = true;
  $('spectrum-wavelength').value = 0;
  status.hidden = false;
  status.textContent = t('palette.loading');
  try {
    const data = await (await api(`/api/jobs/${encodeURIComponent(id)}/palette`)).json();
    if (generation !== resultGeneration) return;
    if (!data.entries.length) throw new Error(t('palette.empty'));
    // Server labels are English; relabel in the UI language, keeping the candidate order.
    data.entries.forEach((entry, index) => { entry.label = entry.pitch_nm === null ? t('palette.blank') : t('palette.candidate', index + 1); });
    const settings = manifest.settings;
    $('spectrum-conditions').textContent = t('spectrum.conditions', settings.theta, settings.modes, settings.step_nm);
    const dimension = value => Number(value.toFixed(3)).toLocaleString('en-US', {maximumFractionDigits: 3});
    const details = entry => entry.pitch_nm === null
      ? t(data.blank_comparison_only ? 'palette.blankOnly' : 'palette.blankStack')
      : t('palette.geometry', dimension(entry.pitch_nm), dimension(entry.width_nm));
    const buttons = data.entries.map((entry, index) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'palette-swatch';
      button.setAttribute('aria-pressed', 'false');
      button.setAttribute('aria-controls', 'spectrum-detail');
      const chip = document.createElement('span');
      chip.className = 'palette-chip';
      chip.style.backgroundColor = entry.hex;
      chip.setAttribute('aria-hidden', 'true');
      const label = document.createElement('strong'); label.textContent = entry.label;
      const geometry = document.createElement('span'); geometry.textContent = details(entry);
      const hex = document.createElement('span'); hex.textContent = entry.hex + (entry.out_of_srgb ? t('palette.gamut') : '');
      button.append(chip, label, geometry, hex);
      button.addEventListener('click', () => select(index));
      return button;
    });
    function select(index) {
      const entry = data.entries[index];
      buttons.forEach((button, i) => button.setAttribute('aria-pressed', String(i === index)));
      $('spectrum-detail').hidden = false;
      $('spectrum-color').style.backgroundColor = entry.hex;
      $('spectrum-title').textContent = t('spectrum.titleOf', entry.label);
      $('spectrum-meta').textContent = `${details(entry)} · ${entry.hex}${entry.out_of_srgb ? t('palette.gamut') : ''}`;
      renderSpectrum(data.wavelength_nm, entry.reflectance);
      updateSpectrumDownload(id, index, data.wavelength_nm, entry);
    }
    swatches.append(...buttons);
    status.hidden = true;
    select(0);
  } catch (error) {
    if (generation !== resultGeneration) return;
    status.textContent = t('palette.error', error.message || error);
  }
}

function renderSpectrum(wavelengths, reflectance) {
  const svg = $('spectrum-chart'), slider = $('spectrum-wavelength');
  currentSpectrum = [wavelengths, reflectance];
  const width = Math.max(360, Math.min(720, svg.clientWidth));
  svg.setAttribute('viewBox', `0 0 ${width} 300`);
  const left = 52, right = width - 20, top = 30, bottom = 246;
  const start = wavelengths[0], end = wavelengths[wavelengths.length - 1];
  const percentages = reflectance.map(value => value * 100);
  const low = Math.min(0, Math.floor(Math.min(...percentages) / 20) * 20);
  const high = Math.max(100, Math.ceil(Math.max(...percentages) / 20) * 20);
  const x = value => left + (value - start) / (end - start || 1) * (right - left);
  const y = value => bottom - (value - low) / (high - low) * (bottom - top);
  function element(name, attrs, text) {
    const node = document.createElementNS('http://www.w3.org/2000/svg', name);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
    if (text !== undefined) node.textContent = text;
    svg.append(node);
    return node;
  }
  svg.replaceChildren();
  element('desc', {id: 'spectrum-description'}, t('spectrum.description', start, end, Math.min(...percentages).toFixed(2), Math.max(...percentages).toFixed(2)));
  element('text', {x: left, y: 17, class: 'spectrum-axis'}, t('spectrum.yAxis'));
  for (let i = 0; i <= 5; i++) {
    const value = low + (high - low) * i / 5;
    element('line', {x1: left, x2: right, y1: y(value), y2: y(value), class: 'spectrum-grid'});
    element('text', {x: left - 10, y: y(value) + 4, 'text-anchor': 'end', class: 'spectrum-axis'}, Number(value.toFixed(1)));
  }
  for (let i = 0; i <= 5; i++) {
    const value = start + (end - start) * i / 5;
    element('line', {x1: x(value), x2: x(value), y1: top, y2: bottom, class: 'spectrum-grid'});
    element('text', {x: x(value), y: bottom + 20, 'text-anchor': 'middle', class: 'spectrum-axis'}, Number(value.toFixed(1)));
  }
  element('text', {x: (left + right) / 2, y: 292, 'text-anchor': 'middle', class: 'spectrum-axis'}, t('spectrum.xAxis'));
  element('path', {d: percentages.map((value, i) => `${i ? 'L' : 'M'}${x(wavelengths[i])},${y(value)}`).join(' '), class: 'spectrum-line'});
  const cursor = element('line', {y1: top, y2: bottom, class: 'spectrum-cursor'});
  const dot = element('circle', {r: 4, class: 'spectrum-dot'});
  function inspect(index) {
    slider.value = index;
    const wavelength = wavelengths[index], value = percentages[index];
    const label = t('spectrum.value', wavelength, value.toFixed(2));
    $('spectrum-value').textContent = label;
    slider.setAttribute('aria-valuetext', label);
    cursor.setAttribute('x1', x(wavelength)); cursor.setAttribute('x2', x(wavelength));
    dot.setAttribute('cx', x(wavelength)); dot.setAttribute('cy', y(value));
  }
  slider.max = wavelengths.length - 1;
  slider.oninput = () => inspect(Number(slider.value));
  svg.onpointermove = event => {
    const matrix = svg.getScreenCTM();
    if (!matrix) return;
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
    if (point.x < left || point.x > right || point.y < top || point.y > bottom) return;
    const wavelength = start + (point.x - left) / (right - left) * (end - start);
    let index = 0;
    for (let i = 1; i < wavelengths.length; i++) {
      if (Math.abs(wavelengths[i] - wavelength) < Math.abs(wavelengths[index] - wavelength)) index = i;
    }
    inspect(index);
  };
  // Keep the chosen wavelength when moving between colors from the same result.
  inspect(Math.min(Number(slider.value), wavelengths.length - 1));
}
