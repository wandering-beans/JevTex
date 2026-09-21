import * as pdfjs from '/vendor/build/pdf.mjs';
pdfjs.GlobalWorkerOptions.workerSrc = '/vendor/build/pdf.worker.mjs';

const $ = id => document.getElementById(id);
const labels = {correct:'正しい', incorrect:'誤り', uncertain:'判断保留', error:'通信・応答エラー'};
let doc = null, pdf = null, status = null, busy = false, renderVersion = 0;
const views = new Map();

function el(tag, text, className) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (className) n.className = className;
  return n;
}
function notice(message) { $('notice').textContent = message; }
async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {
    method:'POST', headers:{'Content-Type':'application/json','X-JevTex-Client':'1'}, body:JSON.stringify(data)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '入力を確認してください。');
  return result;
}
function setBusy(value) {
  busy = value;
  for (const control of document.querySelectorAll('#review button, #review select, #review input, #review textarea, .upload button, #file')) control.disabled = value || control.dataset.unavailable === 'true';
  $('check').disabled = value || !status?.api_key_configured || !doc?.pairs.length;
}
function invalidate() {
  if (!doc) return;
  if (doc.results.length) notice('比較条件を変更しました。判定を再実行してください。');
  doc.results = [];
  $('downloads').hidden = true;
  $('summary').textContent = '';
  document.querySelectorAll('.result, .result-details').forEach(n => n.remove());
  paintHighlights();
}
function equationName(eq) { return `${eq.id} · ${eq.labels[0] || `行${eq.line_start}`} · ${eq.latex.slice(0, 38)}`; }
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
  $('count').textContent = `${doc.equations.length}式 / ${doc.pairs.length}ペア`;
  const byId = Object.fromEntries(doc.equations.map(eq => [eq.id,eq]));
  doc.pairs.forEach((pair, index) => {
    const card = el('article', undefined, 'pair');
    const head = el('div', undefined, 'pair-head');
    const update = key => value => {
      pair[key] = value;
      pair.context_ids = pair.context_ids.filter(id => byId[id].start < byId[pair.after].start && id !== pair.before);
      invalidate(); drawPairs();
    };
    head.append(selectEquation(pair.before, update('before'), `比較ペア${index+1}の式1`), el('span','→'), selectEquation(pair.after, update('after'), `比較ペア${index+1}の式2`));
    const remove = el('button','×','remove'); remove.setAttribute('aria-label',`比較ペア${index+1}を除外`);
    remove.onclick = () => { doc.pairs.splice(index,1); invalidate(); drawPairs(); };
    head.append(remove); card.append(head);
    card.append(el('pre',byId[pair.before].latex+'\n↓\n'+byId[pair.after].latex));
    const context = el('details'); context.append(el('summary','参照式と送信する周辺説明を確認'));
    const definitions = el('div',undefined,'definitions');
    for (const eq of doc.equations.filter(e => e.start < byId[pair.after].start && e.id !== pair.before)) {
      const label = el('label'), input = el('input'); input.type = 'checkbox'; input.checked = pair.context_ids.includes(eq.id);
      input.onchange = () => { pair.context_ids = input.checked ? [...pair.context_ids,eq.id] : pair.context_ids.filter(id => id !== eq.id); invalidate(); };
      label.append(input,el('code',`${eq.id}: ${eq.latex}`)); definitions.append(label);
    }
    context.append(definitions,el('pre',[byId[pair.before].context,byId[pair.after].context].filter(Boolean).join('\n') || '周辺説明なし'));
    card.append(context);
    const result = doc.results[index];
    if (result) {
      const area = el('div',undefined,'result');
      area.append(el('span',labels[result.verdict || 'error'],'badge '+(result.verdict || 'error')));
      if (result.status === 'ok') {
        area.append(el('span',`選択確率 ${Math.round(result.probabilities[result.raw_choice]*100)}%`));
        const jump = el('button',result.locations.length ? 'PDFへ' : '位置未取得'); jump.dataset.unavailable = String(!result.locations.length); jump.disabled = !result.locations.length;
        jump.onclick = () => jumpTo(result.locations[0]); area.append(jump);
      } else { area.append(el('span',result.error)); }
      card.append(area);
      if (result.status === 'ok') {
        const detail = el('details',undefined,'result-details'); detail.append(el('summary','生の判定・確率'));
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
        box.title = `${result.before} → ${result.after}: ${labels[result.verdict]}`; overlay.append(box);
      }
    }
  }
}
async function renderPdf() {
  const version = ++renderVersion;
  views.clear(); $('pdf-pages').replaceChildren();
  if (!pdf) { $('pdf-pages').append(el('p','PDFを生成できませんでした。上のメッセージを確認してください。')); return; }
  const current = pdf;
  for (let page=1;page<=current.numPages;page++) {
    const p = await current.getPage(page); if (version !== renderVersion) return;
    const viewport = p.getViewport({scale:Number($('zoom').value)}), dpr = window.devicePixelRatio || 1;
    const wrapper = el('div',undefined,'pdf-page'), canvas = el('canvas'), overlay = el('div',undefined,'overlay');
    wrapper.style.width = viewport.width+'px'; wrapper.style.height = viewport.height+'px';
    canvas.width = Math.floor(viewport.width*dpr); canvas.height = Math.floor(viewport.height*dpr);
    canvas.style.width = viewport.width+'px'; canvas.style.height = viewport.height+'px'; canvas.setAttribute('aria-label',`PDF ${page}ページ`);
    wrapper.append(canvas,overlay); $('pdf-pages').append(wrapper);
    views.set(page,{wrapper,overlay,viewport,page});
    await p.render({canvas,viewport,transform:dpr === 1 ? null : [dpr,0,0,dpr,0,0]}).promise;
  }
  if (version === renderVersion) paintHighlights();
}
async function loadDocument(input) {
  if (busy) return;
  setBusy(true); notice('TeXを解析・コンパイルしています。初回はフォントの準備で時間がかかります。');
  try {
    const next = await api('/api/documents',input);
    ++renderVersion; if (pdf) await pdf.destroy(); pdf = null; doc = next;
    $('empty-review').hidden = true; $('review').hidden = false; $('downloads').hidden = true;
    $('assumptions').value = ''; $('document-name').textContent = doc.name; $('summary').textContent = '';
    $('warnings').replaceChildren(...doc.warnings.map(w => el('p',w)));
    drawPairs();
    if (doc.pdf_available) pdf = await pdfjs.getDocument({url:`/api/documents/${doc.id}/pdf`,cMapUrl:'/vendor/cmaps/',cMapPacked:true,standardFontDataUrl:'/vendor/standard_fonts/',wasmUrl:'/vendor/wasm/',isEvalSupported:false}).promise;
    await renderPdf();
    notice('読み込み完了。比較ペア・参照式・前提条件を確認してください。まだJevには送信していません。');
  } catch (error) { notice(error.message); }
  finally { setBusy(false); }
}
$('file').onchange = async event => {
  const file = event.target.files[0]; if (!file) return;
  if (file.size > 1_000_000) { notice('TeXは1MB以下にしてください。'); return; }
  try { await loadDocument({name:file.name,source:new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer())}); }
  catch { notice('UTF-8形式のTeXファイルを選んでください。'); }
  event.target.value = '';
};
for (const variant of ['correct','mistake']) $(variant).onclick = async () => {
  try { await loadDocument(await api('/api/samples/'+variant)); } catch(error) { notice(error.message); }
};
$('add-pair').onclick = () => {
  if (doc.equations.length < 2) return;
  doc.pairs.push({before:doc.equations[0].id, after:doc.equations[1].id, context_ids:[]}); invalidate(); drawPairs();
};
$('assumptions').oninput = invalidate;
$('show-highlights').onchange = paintHighlights;
$('zoom').onchange = () => renderPdf().catch(e => notice(e.message));
$('check').onclick = async () => {
  setBusy(true); notice(`${doc.pairs.length}ペアをJevで判定しています。完了するまでお待ちください。`);
  try {
    doc = await api(`/api/documents/${doc.id}/check`,{pairs:doc.pairs, assumptions:$('assumptions').value});
    drawPairs(); paintHighlights();
    const counts = {};
    for (const r of doc.results) { const label = labels[r.verdict || 'error']; counts[label] = (counts[label] || 0)+1; }
    $('summary').textContent = Object.entries(counts).map(([k,v]) => `${k} ${v}`).join(' / ');
    $('download-pdf').href = `/api/documents/${doc.id}/pdf?annotated=true`; $('download-pdf').hidden = !doc.pdf_available;
    $('download-json').href = `/api/documents/${doc.id}/results`; $('downloads').hidden = false;
    notice('判定完了。変形後の式を、誤りは赤、判断保留は黄色で表示します。');
  } catch(error) { notice(error.message); }
  finally { setBusy(false); }
};
try {
  status = await api('/api/status');
  $('connection').textContent = status.api_key_configured ? 'Jev 接続キー設定済み' : 'ローカル · APIキー未設定';
  $('model').textContent = `${status.model} / 暫定閾値 ${status.threshold}`;
  $('key-help').textContent = status.api_key_configured ? '選択した式・参照式・前提・周辺説明をTypeSafeへ送信します。' : 'サーバーの環境変数 TYPESAFE_API_KEY を設定して再起動すると、判定できます。';
  setBusy(false);
} catch(error) { notice(error.message); }
