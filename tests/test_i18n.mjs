import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createI18n} from '../static/i18n.mjs';

const catalogs = JSON.parse(readFileSync(new URL('../static/locales.json',import.meta.url),'utf8'));
const keys = Object.keys(catalogs.ja.messages).sort();
const placeholders = text => [...text.matchAll(/\{(\w+)\}/g)].map(m=>m[1]).sort();
for (const [lang,catalog] of Object.entries(catalogs)) {
  assert.ok(catalog.name);
  assert.deepEqual(Object.keys(catalog.messages).sort(),keys,lang);
  for (const key of keys) {
    assert.ok(catalog.messages[key].trim(),`${lang}: ${key}`);
    assert.deepEqual(placeholders(catalog.messages[key]),placeholders(catalogs.ja.messages[key]),key);
  }
}
const i18n = createI18n(catalogs,'en');
assert.equal(i18n.t('counts',{equations:11,pairs:8}),'11 equations / 8 pairs');
const params = {ids:'e1, e2',environment:'gather',code:503,document:'document'};
for (const key of keys.filter(key=>key.startsWith('server.'))) {
  const raw = catalogs.ja.messages[key].replace(/\{(\w+)\}/g,(_,name)=>params[name]);
  assert.equal(i18n.serverMessage(raw),i18n.t(key,params),key);
}
assert.equal(i18n.serverMessage('unknown diagnostic'),'unknown diagnostic');
i18n.setLanguage('ja');
assert.equal(i18n.t('uncertain'),'判断保留');
i18n.setLanguage('missing');
assert.equal(i18n.language,'ja');
const extra = {...catalogs,fr:{name:'Français',messages:{check:'Vérifier'}}};
const french = createI18n(extra,'fr');
assert.equal(french.t('check'),'Vérifier');
assert.equal(french.t('uncertain'),catalogs.ja.messages.uncertain);
const html = readFileSync(new URL('../static/index.html',import.meta.url),'utf8');
for (const [,key] of html.matchAll(/data-i18n(?:-placeholder|-aria-label)?="([^"]+)"/g)) {
  assert.ok(keys.includes(key),key);
}
console.log('Locale coverage, placeholders, server messages, fallback, and HTML keys: OK');
