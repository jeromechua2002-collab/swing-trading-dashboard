const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('sector-breadth.html','utf8');
const core=JSON.parse(fs.readFileSync('data/rrg-core.json','utf8'));
const marker=html.match(/const vehicleToUnderlying=\{[^;]+;const industryByStock=\{[^;]+;const sectorByIndustry=\{[^;]+;/);
assert.ok(marker,'Missing ticker mapping source');
const {vehicleToUnderlying,industryByStock,sectorByIndustry}=vm.runInNewContext(marker[0]+';({vehicleToUnderlying,industryByStock,sectorByIndustry})');
const pairs={XLK:'RSPT',XLY:'RSPD',XLC:'RSPC',XLU:'RSPU',XLRE:'RSPR',XLP:'RSPS',XLI:'RSPN',XLB:'RSPM',XLF:'RSPF',XLV:'RSPH',XLE:'RSPG'};
const group=core.universes.stock_members;
const memberships={};
for(const [sector,stocks] of Object.entries(group)){
 assert.ok(pairs[sector],'Unknown sector '+sector);
 for(const ticker of stocks){assert.equal(memberships[ticker],undefined,'Duplicate stock '+ticker);memberships[ticker]=sector;}
}
assert.equal(Object.keys(memberships).length,116,'Stock coverage changed unexpectedly');
const industries=Object.values(core.universes.industries).flat();
assert.equal(industries.length,16);
for(const t of industries) assert.ok(pairs[sectorByIndustry[t]],'Industry '+t+' lacks valid sector mapping');
for(const [vehicle,underlying] of Object.entries(vehicleToUnderlying))
 assert.ok(pairs[memberships[underlying]||sectorByIndustry[underlying]||underlying],'Unmapped vehicle '+vehicle+' → '+underlying);
for(const t of ['PANW','CRWD','AMZN','GOOG','COP','XOM','JPM','GS','MU','AMD','NVDA'])
 assert.ok(pairs[memberships[t]],'Weekly watchlist missing '+t);
assert.equal(memberships.AMZN,'XLY');
assert.equal(memberships.PANW,'XLK');
assert.equal(memberships.CRWD,'XLK');
assert.equal(memberships.GOOG,'XLC');
assert.equal(memberships.MU,'XLK');
assert.equal(sectorByIndustry.SMH,'XLK');
assert.ok(html.includes('id="marketRows"')&&html.includes('id="tickerSearch"'),'Missing market scanner UI');
console.log('Ticker coverage PASSED: '+Object.keys(memberships).length+' stock tickers, '+industries.length+' industries, '+Object.keys(pairs).length+' sector pairs, '+Object.keys(vehicleToUnderlying).length+' leveraged aliases; weekly shortlist mapped');
