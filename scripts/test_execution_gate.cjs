const assert=require('node:assert/strict'),lib=require('../trade-gate.js');
function sample(){return {ticker:"MRK",vehicleType:"stock",entry:100,stop:97,target1:109,quantity:10,entryFee:2.3,exitFee:2.3,roundTripSlipPerShare:0.1,cashUSD:3000,maxLossUSD:80,plannedSession:"RTH",overnightHold:false,stopCoverage:"RTH-only",gapRiskAccepted:false,marketRegimeChecked:true,quoteChecked:true,underlyingChecked:true,relativeVolumeChecked:true,liquidityChecked:true,pivotVerified:true,firstTargetVerified:true,triggerConfirmed:true,catalystChecked:true,stopEligibilityVerified:true};}
const ok=lib.evaluate(sample());assert.match(ok.status,/CONDITIONALLY ELIGIBLE/);assert.equal(ok.calculations.netRisk,35.6);assert.equal(ok.calculations.netReward,84.4);assert.equal(ok.calculations.netRR,2.371);
const blocks=[
 [{target1:107},/below the manual/],
 [{stopCoverage:"unknown"},/unverified/],
 [{plannedSession:"overnight"},/does not include planned/],
 [{overnightHold:true},/overnight hold lacks verified protection/i],
 [{quantity:50},/cash budget|loss budget/],
 [{maxLossUSD:20},/loss budget/],
 [{quoteChecked:false},/checklist/],
 [{pivotVerified:false},/checklist/],
 [{firstTargetVerified:false},/checklist/],
 [{catalystChecked:false},/checklist/],
 [{stop:101},/stop below entry/],
 [{target1:98},/must exceed entry/],
 [{entry:-3},/positive/],
 [{quantity:1.5},/whole shares/],
 [{roundTripSlipPerShare:10},/eliminated by costs|below the manual/],
 [{vehicleType:"wrong"},/actual traded vehicle/]
 ];
for(const [change,pattern] of blocks){const out=lib.evaluate({...sample(),...change});assert.doesNotMatch(out.status,/CONDITIONALLY/);assert.ok(out.errors.some(e=>pattern.test(e)),JSON.stringify({change,out}));}
const overnight=lib.evaluate({...sample(),plannedSession:"overnight",overnightHold:true,stopCoverage:"all-planned-hours",gapRiskAccepted:true});assert.match(overnight.status,/CONDITIONALLY/);
const unprotected=lib.evaluate({...sample(),plannedSession:"RTH",overnightHold:true,stopCoverage:"RTH-only"});assert.match(unprotected.status,/BLOCKED/);
const eventGate=lib.evaluate({...sample(),eventBeforeExit:true,eventRiskPlanVerified:false});assert.equal(eventGate.status,"BLOCKED");
const countertrendGate=lib.evaluate({...sample(),setupType:"countertrend"});assert.equal(countertrendGate.status,"BLOCKED");
const missing=lib.evaluate({...sample(),entry:NaN});assert.equal(missing.status,"INCOMPLETE");
const empty=lib.evaluate({...sample(),quantity:0});assert.equal(empty.status,"INCOMPLETE");
console.log("Execution risk gate PASS: fee/slippage-aware 2R, cash and loss limits, broker-hour stop protection, gap risk, factual checks, missing/inverted values");
