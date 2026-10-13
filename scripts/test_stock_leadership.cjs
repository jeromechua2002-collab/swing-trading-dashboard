const assert=require('node:assert/strict'),fs=require('node:fs'),lib=require('../stock-leadership.js');
const core=JSON.parse(fs.readFileSync('data/rrg-core.json','utf8'));
assert.equal(Object.keys(core.universes.stock_members).length,11);
let count=0;
for(const sector of Object.keys(core.universes.stock_members)){
 const x=JSON.parse(fs.readFileSync('data/stocks/'+sector+'.json','utf8'));
 const got=lib.rank(core,x,sector);
 assert.equal(got.rows.length,x.members.length);count+=got.rows.length;
 assert.deepEqual(new Set(got.rows.map(x=>x.ticker)),new Set(x.members));
 for(const row of got.rows){
   assert.ok(['Leading','Weakening','Improving','Lagging'].includes(row['1D_sector'].q));
   assert.ok(['Leading','Weakening','Improving','Lagging'].includes(row['4H_sector'].q));
   assert.ok(Number.isFinite(row['1D_sector'].dr));assert.ok(row.phase);
 }
}
assert.equal(count,116,'Every configured ticker must be tested');
const xl=JSON.parse(fs.readFileSync('data/stocks/XLV.json','utf8'));
const v=lib.rank(core,xl,'XLV');assert.equal(v.rows.length,10);
for(const t of ['ABBV','JNJ','MRK','ABT','UNH','ISRG','LLY','TMO','AMGN','GILD'])assert.ok(v.rows.some(x=>x.ticker===t));
const corrupt=structuredClone(xl);delete corrupt.timeframes['4H'].stock.vs_XLV.JNJ;
assert.throws(()=>lib.rank(core,corrupt,'XLV'),/Incomplete RRG trail/);
const outdated=structuredClone(xl);outdated.generated_at='2026-01-01T00:00:00Z';assert.throws(()=>lib.rank(core,outdated,'XLV'),/mismatch/);
const mismatch=structuredClone(xl);mismatch.members.pop();assert.throws(()=>lib.rank(core,mismatch,'XLV'),/membership/);
const wrongDay=structuredClone(xl);wrongDay.timeframes['1D'].stock.vs_XLV.JNJ[15].time='2024-01-01T00:00:00+00:00';assert.throws(()=>lib.rank(core,wrongDay,'XLV'),/dates are invalid|differs/);
assert.equal(lib.quadrant({ratio:101,momentum:101}),'Leading');
assert.equal(lib.quadrant({ratio:99,momentum:101}),'Improving');
assert.equal(lib.quadrant({ratio:101,momentum:99}),'Weakening');
assert.equal(lib.quadrant({ratio:99,momentum:99}),'Lagging');
console.log('STOCK LEADERSHIP VALIDATED: '+count+' individual tickers across 11 sectors including all 10 healthcare names; stale, missing, mismatched and future sessions fail closed');

const html=fs.readFileSync('stock-leadership.html','utf8');
for(const tag of ['id="sector"','id="filter"','id="rows"','id="session"','stock-leadership.js'])assert.ok(html.includes(tag),'Missing stock leadership UI '+tag);
for(const m of html.matchAll(/<script(?:[^>]*?)>([\s\S]*?)<\/script>/g))if(m[1].trim())new Function(m[1]);
console.log('Stock Leadership frontend inline-script syntax and controls validated');
