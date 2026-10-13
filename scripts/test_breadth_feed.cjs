const assert=require('node:assert/strict'),fs=require('node:fs');
const validate=require('../breadth-feed.js');
const good=JSON.parse(fs.readFileSync(process.argv[2]||'/tmp/breadth-test.json','utf8'));
const now=Date.parse(good.generated_at);assert.equal(validate(good,now),good);let count=1;
const faults={
 malformedBuild:d=>d.generated_at='nonsense',futureBuild:d=>d.generated_at=new Date(now+600000).toISOString(),staleBuild:d=>d.generated_at=new Date(now-73*3600000).toISOString(),
 malformedSource:d=>d.source_generated_at='bad',staleSource:d=>d.source_generated_at=new Date(now-73*3600000).toISOString(),
 duplicatePair:d=>d.rows[1]=d.rows[0],wrongPair:d=>d.rows[0].equal='RSPG',missingPair:d=>d.rows.pop(),
 staleSession:d=>d.as_of='2026-09-01',futureSession:d=>d.as_of='2030-01-01',invalidMetric:d=>d.rows[0].metrics['20'].cap_vs_spy=NaN,
 missingWindow:d=>delete d.rows[0].metrics['60'],wrongState:d=>d.rows[0].metrics['5'].state='buy now',
 wrongQuadrant:d=>d.rows[0].equal_quadrant='bad',wrongTrailDate:d=>d.rrg.equal_vs_SPY.RSPT.at(-1).time='2026-09-01',
 missingTail:d=>d.rrg.equal_vs_SPY.RSPT.pop(),nonfiniteTrail:d=>d.rrg.equal_vs_SPY.RSPT[0].ratio=Infinity,
 missingPrice:d=>d.prices.RSPT.pop(),zeroPrice:d=>d.prices.RSPT[0].close=0,wrongPriceDate:d=>d.prices.RSPT[0].time='2026-01-01',
 unavailable:d=>d.status='unavailable',nanPrice:d=>d.prices.RSPT[0].close=NaN
};
for(const [name,mutate] of Object.entries(faults)){const d=structuredClone(good);mutate(d);assert.throws(()=>validate(d,now),undefined,name);count++;}
console.log(count+' client feed corruption checks passed');
