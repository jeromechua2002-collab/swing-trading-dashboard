const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {rotation,confirmation}=require('../breadth-confirmation.js');
const up=Array.from({length:16},(_,i)=>({ratio:98.5+.09*i,momentum:99.3+.14*i}));
const down=Array.from({length:16},(_,i)=>({ratio:101.5-.09*i,momentum:101.4-.14*i}));
const flat=Array.from({length:16},()=>({ratio:100.2,momentum:99.9}));
const prices=Array.from({length:100},(_,i)=>({time:String(i),close:100+i}));
function data(c,e){return {rows:[{cap:'XLK',equal:'RSPT',metrics:Object.fromEntries([5,10,20,60].map(n=>[n,{equal_vs_cap:1}]))}],prices:{XLK:prices},rrg:{cap_vs_SPY:{XLK:c},equal_vs_RSP:{RSPT:e},equal_vs_SPY:{RSPT:down}}};}
let count=0;function test(name,f){f();count++;}
test('broad long',()=>assert.equal(confirmation(data(up,up),'XLK','long').tone,'support'));
test('broad short',()=>assert.equal(confirmation(data(down,down),'XLK','short').tone,'support'));
test('opposes long',()=>assert.equal(confirmation(data(down,down),'XLK','long').tone,'conflict'));
test('opposes short',()=>assert.equal(confirmation(data(up,up),'XLK','short').tone,'conflict'));
test('narrow large-name leadership',()=>assert.match(confirmation(data(up,down),'XLK','long').label,/Partial support/));
test('equal weight recovery first',()=>assert.match(confirmation(data(down,up),'XLK','long').label,/Equal weight moves first/));
test('flat tails no confirmation',()=>assert.equal(confirmation(data(flat,flat),'XLK','long').tone,'mixed'));
test('Leading does not mean improving',()=>{const t=down.map(p=>({...p,ratio:p.ratio+1,momentum:p.momentum+1}));assert.equal(rotation(t).quadrant,'Leading');assert.equal(rotation(t).direction,'deteriorating')});
test('benchmark lens changes answer independently',()=>{const d=data(up,up);assert.equal(confirmation(d,'XLK','long','video').tone,'support');assert.equal(confirmation(d,'XLK','long','common').tone,'partial')});
test('industry scope cannot pretend direct confirmation',()=>assert.match(confirmation(data(up,up),'XLK','long','video','industry').caveat,/does not directly confirm/));
test('single stock scope remains context',()=>assert.match(confirmation(data(up,up),'XLK','long','video','stock').caveat,/single stock can differ/));
test('falling absolute price retained',()=>{const d=data(up,up);d.prices.XLK=prices.map(p=>({...p,close:300-p.close}));const v=confirmation(d,'XLK','long');assert.equal(v.tone,'support');assert.match(v.priceNote,/disagree/)});
test('invalid thesis rejected',()=>assert.throws(()=>confirmation(data(up,up),'XLK','BUY')));
test('bad tail rejected',()=>assert.throws(()=>rotation([{ratio:1,momentum:2}])));
class Node{constructor(){this.style={};this.dataset={};this.value='';this.textContent='';this.children=[];this.classes=new Set();this.classList={toggle:(key,on)=>on?this.classes.add(key):this.classes.delete(key)}}setAttribute(){}appendChild(n){this.children.push(n)}addEventListener(){}}
async function ui(){const nodes={};const $=id=>nodes[id]??=new Node();for(const [id,v] of Object.entries({source:'lesson',pair:'XLK',thesis:'long',scope:'sector',scenario:'broad',lens:'video',window:'20',liveLens:'video',liveWindow:'20'}))$(id).value=v;const ctx={document:{getElementById:$,querySelectorAll:()=>[],addEventListener(){}},Date,console,setInterval(){},fetch:async()=>({ok:false,status:404})};vm.createContext(ctx);vm.runInContext(fs.readFileSync('breadth-feed.js','utf8'),ctx);vm.runInContext(fs.readFileSync('breadth-confirmation.js','utf8'),ctx);vm.runInContext(fs.readFileSync('sector-breadth.html','utf8').match(/<script>([\s\S]*)<\/script>/)[1],ctx);await new Promise(r=>setTimeout(r,10));
assert.match($('answer').textContent,/Both rotations support/);assert.match($('status').textContent,/LESSON MODE/);assert.ok($('performance').innerHTML.includes('polyline'));count+=3;
vm.runInContext("$('scenario').value='weak';$('thesis').value='short';render()",ctx);assert.match($('answer').textContent,/support your short/);count++;
vm.runInContext("$('scope').value='industry';render()",ctx);assert.match($('scopeNote').textContent,/does not directly confirm/);count++;
vm.runInContext("$('source').value='live';render()",ctx);assert.ok($('output').classes.has('hidden'));assert.match($('status').textContent,/not available/);count+=2;
console.log(count+' confirmation and interface checks passed');}
ui().catch(e=>{console.error(e);process.exit(1)});
