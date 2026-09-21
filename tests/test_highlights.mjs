// Exercise the actual renderer with a minimal DOM, without an API call.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../static/app.js', import.meta.url), 'utf8');
const render = source.slice(source.indexOf('function viewportRect('), source.indexOf('async function renderPdf('));
const toggle = {checked:true};
const overlay = {children:[], replaceChildren(){this.children=[];}, append(n){this.children.push(n);}};
let scale = 1;
const result = (verdict, y, status='ok', page=1) => ({verdict,status,before:'e1',after:'e2',locations:[{page,rect:[10,y,150,y+20]}]});
const context = vm.createContext({
  $:()=>toggle, labels:{incorrect:'誤り',uncertain:'判断保留'},
  el:(_tag,_text,className)=>({className,style:{}}),
  views:new Map([[1,{overlay,page:1,viewport:{convertToViewportPoint:(x,y)=>[x*scale,(800-y)*scale]}}]]),
  doc:{results:[result('uncertain',10),result('incorrect',10),result('uncertain',40),
    result('correct',70),result('uncertain',100,'error'),result('uncertain',130,'ok',2),
    {...result('uncertain',160),locations:[]}]}
});
vm.runInContext(render+'\npaintHighlights();',context);
assert.deepEqual(overlay.children.map(n=>n.className),['highlight incorrect','highlight uncertain']);
assert.match(overlay.children[1].title,/判断保留/);
assert.equal(overlay.children[1].style.width,'140px');
scale=1.5;
vm.runInContext('paintHighlights()',context);
assert.equal(overlay.children[1].style.width,'210px');
assert.equal(overlay.children[1].style.top,'1110px');
toggle.checked=false;
vm.runInContext('paintHighlights()',context);
assert.equal(overlay.children.length,0);
toggle.checked=true;
vm.runInContext('paintHighlights()',context);
assert.equal(overlay.children.length,2);
console.log('Highlight colors, precedence, zoom, visibility, and exclusions: OK');
