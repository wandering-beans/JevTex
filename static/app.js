import {createI18n} from '/static/i18n.mjs';
import * as pdfjs from '/vendor/build/pdf.mjs';
pdfjs.GlobalWorkerOptions.workerSrc = '/vendor/build/pdf.worker.mjs';

const $ = id => document.getElementById(id);
const catalogs = await fetch('/static/locales.json').then(response => {
  if (!response.ok) throw new Error('Could not load translations');
  return response.json();
});
let savedLanguage = 'ja';
try { savedLanguage = localStorage.getItem('jevtex.language') || 'ja'; } catch {}
const i18n = createI18n(catalogs, savedLanguage);
const t = (key, params) => i18n.t(key, params);
let currentNotice = {key:'initial', params:{}};
let doc = null, pdf = null, status = null, busy = false, renderVersion = 0;
const views = new Map();

function el(tag, text, className) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (className) n.className = className;
  return n;
}
function notice(key, params = {}) {
  currentNotice = {key, params};
  $('notice').textContent = t(key, params);
}
function showError(error) {
  if (error.uiKey) { notice(error.uiKey); return; }
  currentNotice = {message:error.message};
  $('notice').textContent = i18n.serverMessage(error.message);
}
async function api(path, data) {
  let response;
  try { response = await fetch(path, data === undefined ? {} : {
    method:'POST', headers:{'Content-Type':'application/json','X-JevTex-Client':'1'}, body:JSON.stringify(data)
  }); } catch { const error = new Error(); error.uiKey = 'networkError'; throw error; }
  const result = await response.json();
  if (!response.ok) {
    const error = new Error(typeof result.detail === 'string' ? result.detail : '');
    if (!error.message) error.uiKey = 'invalidInput';
    throw error;
  }
  return result;
}
function setBusy(value) {
  busy = value;
  for (const control of document.querySelectorAll('#review button, #review select, #review input, #review textarea, .upload button, #file')) control.disabled = value || control.dataset.unavailable === 'true';
  $('check').disabled = value || !status?.api_key_configured || !doc?.pairs.length;
}
function invalidate() {
  if (!doc) return;
  if (doc.results.length) notice('conditionsChanged');
  doc.results = [];
  $('downloads').hidden = true;
  $('summary').textContent = '';
  document.querySelectorAll('.result, .result-details').forEach(n => n.remove());
  paintHighlights();
}
function equationName(eq) { return `${eq.id} · ${eq.labels[0] || t('line',{line:eq.line_start})} · ${eq.latex.slice(0, 38)}`; }
function selectEquation(id, onChange, name) {
  const select = el('select');
  select.setAttribute('aria-label', name);
  doc.equations.forEach(eq => { const o = el('option', equationName(eq)); o.value = eq.id; select.append(o); });
  select.value = id;
  select.addEventListener('change', () => onChange(select.value));
  return select;
}
function drawPairs() {
  $('pairs').replaceChildren();
  $('count').textContent = t('counts',{equations:doc.equations.length,pairs:doc.pairs.length});
  const byId = Object.fromEntries(doc.equations.map(eq => [eq.id,eq]));
  doc.pairs.forEach((pair, index) => {
    const card = el('article', undefined, 'pair');
    const head = el('div', undefined, 'pair-head');
    const update = key => value => {
      pair[key] = value;
      pair.context_ids = pair.context_ids.filter(id => byId[id].start < byId[pair.after].start && id !== pair.before);
      invalidate(); drawPairs();
    };
    head.append(selectEquation(pair.before, update('before'), t('pairEquation',{pair:index+1,equation:1})), el('span','→'), selectEquation(pair.after, update('after'), t('pairEquation',{pair:index+1,equation:2})));
    const remove = el('button','×','remove'); remove.setAttribute('aria-label',t('removePair',{pair:index+1}));
    remove.onclick = () => { doc.pairs.splice(index,1); invalidate(); drawPairs(); };
    head.append(remove); card.append(head);
    card.append(el('pre',byId[pair.before].latex+'\n↓\n'+byId[pair.after].latex));
    const context = el('details'); context.append(el('summary',t('context')));
    const definitions = el('div',undefined,'definitions');
    for (const eq of doc.equations.filter(e => e.start < byId[pair.after].start && e.id !== pair.before)) {
      const label = el('label'), input = el('input'); input.type = 'checkbox'; input.checked = pair.context_ids.includes(eq.id);
      input.onchange = () => { pair.context_ids = input.checked ? [...pair.context_ids,eq.id] : pair.context_ids.filter(id => id !== eq.id); invalidate(); };
      label.append(input,el('code',`${eq.id}: ${eq.latex}`)); definitions.append(label);
    }
    context.append(definitions,el('pre',[byId[pair.before].context,byId[pair.after].context].filter(Boolean).join('\n') || t('noContext')));
    card.append(context);
    const result = doc.results[index];
    if (result) {
      const area = el('div',undefined,'result');
      area.append(el('span',t(result.verdict || 'error'),'badge '+(result.verdict || 'error')));
      if (result.status === 'ok') {
        area.append(el('span',t('probability',{percent:Math.round(result.probabilities[result.raw_choice]*100)})));
        const jump = el('button',t(result.locations.length ? 'jump' : 'noLocation')); jump.dataset.unavailable = String(!result.locations.length); jump.disabled = !result.locations.length;
        jump.onclick = () => jumpTo(result.locations[0]); area.append(jump);
      } else { area.append(el('span',i18n.serverMessage(result.error))); }
      card.append(area);
      if (result.status === 'ok') {
        const detail = el('details',undefined,'result-details'); detail.append(el('summary',t('rawResult')));
        detail.append(el('pre',JSON.stringify({raw_choice:result.raw_choice, probabilities:result.probabilities, confidence:result.confidence, threshold:result.threshold, model:result.model},null,2)));
        card.append(detail);
      }
    }
    $('pairs').append(card);
  });
  setBusy(busy);
}
function jumpTo(location) {
  if (!location) return;
  const v = views.get(location.page); if (!v) return;
  const rect = viewportRect(v.viewport, location.rect);
  $('pdf-pages').scrollTo({top:v.wrapper.offsetTop-$('pdf-pages').offsetTop+Math.min(rect[1],rect[3])-100, behavior:'smooth'});
}
function viewportRect(viewport, rect) {
  return [...viewport.convertToViewportPoint(rect[0],rect[1]), ...viewport.convertToViewportPoint(rect[2],rect[3])];
}
function paintHighlights() {
  for (const {overlay,viewport,page} of views.values()) {
    overlay.replaceChildren();
    if (!$('show-highlights').checked || !doc) continue;
    const seen = new Set();
    // Match saved PDF precedence: red wins over yellow for the same equation.
    for (const result of doc.results.filter(r => r.status === 'ok' && ['incorrect','uncertain'].includes(r.verdict))
      .sort((a,b) => Number(a.verdict !== 'incorrect') - Number(b.verdict !== 'incorrect'))) {
      for (const loc of result.locations.filter(l => l.page === page)) {
        const key = loc.rect.join(','); if (seen.has(key)) continue; seen.add(key);
        const r = viewportRect(viewport,loc.rect), box = el('div',undefined,'highlight '+result.verdict);
        Object.assign(box.style,{left:Math.min(r[0],r[2])+'px', top:Math.min(r[1],r[3])+'px', width:Math.abs(r[2]-r[0])+'px', height:Math.abs(r[3]-r[1])+'px'});
        box.title = `${result.before} → ${result.after}: ${t(result.verdict)}`; overlay.append(box);
      }
    }
  }
}
async function renderPdf() {
  const version = ++renderVersion;
  views.clear(); $('pdf-pages').replaceChildren();
  if (!pdf) { const message = el('p',t('pdfFailed')); message.dataset.i18n = 'pdfFailed'; $('pdf-pages').append(message); return; }
  const current = pdf;
  for (let page=1;page<=current.numPages;page++) {
    const p = await current.getPage(page); if (version !== renderVersion) return;
    const viewport = p.getViewport({scale:Number($('zoom').value)}), dpr = window.devicePixelRatio || 1;
    const wrapper = el('div',undefined,'pdf-page'), canvas = el('canvas'), overlay = el('div',undefined,'overlay');
    wrapper.style.width = viewport.width+'px'; wrapper.style.height = viewport.height+'px';
    canvas.width = Math.floor(viewport.width*dpr); canvas.height = Math.floor(viewport.height*dpr);
    canvas.style.width = viewport.width+'px'; canvas.style.height = viewport.height+'px'; canvas.setAttribute('aria-label',t('pdfPage',{page}));
    wrapper.append(canvas,overlay); $('pdf-pages').append(wrapper);
    views.set(page,{wrapper,overlay,viewport,page});
    await p.render({canvas,viewport,transform:dpr === 1 ? null : [dpr,0,0,dpr,0,0]}).promise;
  }
  if (version === renderVersion) paintHighlights();
}
async function loadDocument(input) {
  if (busy) return;
  setBusy(true); notice('compiling');
  try {
    const next = await api('/api/documents',input);
    ++renderVersion; if (pdf) await pdf.destroy(); pdf = null; doc = next;
    $('empty-review').hidden = true; $('review').hidden = false; $('downloads').hidden = true;
    $('assumptions').value = ''; $('document-name').textContent = doc.name; $('summary').textContent = '';
    $('warnings').replaceChildren(...doc.warnings.map(w => el('p',i18n.serverMessage(w))));
    drawPairs();
    if (doc.pdf_available) pdf = await pdfjs.getDocument({url:`/api/documents/${doc.id}/pdf`,cMapUrl:'/vendor/cmaps/',cMapPacked:true,standardFontDataUrl:'/vendor/standard_fonts/',wasmUrl:'/vendor/wasm/',isEvalSupported:false}).promise;
    await renderPdf();
    notice('loaded');
  } catch (error) { showError(error); }
  finally { setBusy(false); }
}
function drawSummary() {
  const counts = {};
  for (const r of doc?.results || []) { const key = r.verdict || 'error'; counts[key] = (counts[key] || 0)+1; }
  $('summary').textContent = Object.entries(counts).map(([key,n]) => `${t(key)} ${n}`).join(' / ');
}
function refreshLanguage() {
  document.documentElement.lang = i18n.language;
  $('language').value = i18n.language;
  i18n.apply(document);
  if (currentNotice.key) notice(currentNotice.key, currentNotice.params);
  else $('notice').textContent = i18n.serverMessage(currentNotice.message);
  if (status) {
    $('connection').textContent = t(status.api_key_configured ? 'keySet' : 'keyUnset');
    $('model').textContent = t('model',status);
    $('key-help').textContent = t(status.api_key_configured ? 'keyHelpSet' : 'keyHelpUnset');
  }
  if (doc) {
    const open = [...$('pairs').querySelectorAll('details')].map(node => node.open);
    drawPairs();
    $('pairs').querySelectorAll('details').forEach((node,index) => { node.open = open[index] || false; });
    $('document-name').textContent = doc.name;
    $('warnings').replaceChildren(...doc.warnings.map(w => el('p',i18n.serverMessage(w))));
  }
  drawSummary();
  for (const {wrapper,page} of views.values()) wrapper.querySelector('canvas').setAttribute('aria-label',t('pdfPage',{page}));
  paintHighlights();
}
for (const [code, catalog] of Object.entries(catalogs)) {
  const option = el('option',catalog.name); option.value = code; $('language').append(option);
}
$('language').onchange = () => {
  i18n.setLanguage($('language').value);
  try { localStorage.setItem('jevtex.language',i18n.language); } catch {}
  refreshLanguage();
};
refreshLanguage();

$('file').onchange = async event => {
  const file = event.target.files[0]; if (!file) return;
  if (file.size > 1_000_000) { notice('fileTooLarge'); return; }
  try { await loadDocument({name:file.name,source:new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer())}); }
  catch { notice('utf8'); }
  event.target.value = '';
};
for (const variant of ['correct','mistake']) $(variant).onclick = async () => {
  try { await loadDocument(await api('/api/samples/'+variant)); } catch(error) { showError(error); }
};
$('add-pair').onclick = () => {
  if (doc.equations.length < 2) return;
  doc.pairs.push({before:doc.equations[0].id, after:doc.equations[1].id, context_ids:[]}); invalidate(); drawPairs();
};
$('assumptions').oninput = invalidate;
$('show-highlights').onchange = paintHighlights;
$('zoom').onchange = () => renderPdf().catch(e => showError(e));
$('check').onclick = async () => {
  setBusy(true); notice('checking',{pairs:doc.pairs.length});
  try {
    doc = await api(`/api/documents/${doc.id}/check`,{pairs:doc.pairs, assumptions:$('assumptions').value});
    drawPairs(); paintHighlights();
    drawSummary();
    $('download-pdf').href = `/api/documents/${doc.id}/pdf?annotated=true`; $('download-pdf').hidden = !doc.pdf_available;
    $('download-json').href = `/api/documents/${doc.id}/results`; $('downloads').hidden = false;
    notice('checked');
  } catch(error) { showError(error); }
  finally { setBusy(false); }
};
try {
  status = await api('/api/status');
  refreshLanguage();
  setBusy(false);
} catch(error) { showError(error); }
