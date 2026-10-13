/* Deterministic, broker-agnostic pre-trade risk gate. No live execution. */
(function(root){
 "use strict";
 const REQUIRED=["marketRegimeChecked","quoteChecked","underlyingChecked","pivotVerified","firstTargetVerified","triggerConfirmed","catalystChecked","relativeVolumeChecked","liquidityChecked","stopEligibilityVerified"];
 const finitePositive=v=>typeof v==="number"&&Number.isFinite(v)&&v>0;
 function evaluate(v){
   const errors=[],pending=[];
   const nums=["entry","stop","target1","quantity","entryFee","exitFee","roundTripSlipPerShare","cashUSD","maxLossUSD"];
   for(const key of nums){
     if(typeof v[key]!=="number"||!Number.isFinite(v[key])||v[key] < 0 || (["entry","stop","target1","quantity","cashUSD","maxLossUSD"].includes(key)&&v[key]===0))errors.push(key+" must be a valid positive amount");
   }
   if(errors.length) return {status:"INCOMPLETE",errors,pending,calculations:null};
   if(!Number.isSafeInteger(v.quantity)||v.quantity<1)errors.push("Quantity must be whole shares");
   if(v.stop>=v.entry)errors.push("A purchased long position requires stop below entry");
   if(v.target1<=v.entry)errors.push("First credible target must exceed entry");
   if(!["stock","leveragedETF","inverseETF"].includes(v.vehicleType))errors.push("Select the actual traded vehicle");
   if(!["RTH","overnight","extended"].includes(v.plannedSession))errors.push("Select intended session");
   if(!["RTH-only","all-planned-hours","unknown"].includes(v.stopCoverage))errors.push("Select the broker's verified stop session coverage");
   if(v.stopCoverage==="unknown")errors.push("Stop trigger/session eligibility is unverified");
   if((v.plannedSession==="overnight"||v.plannedSession==="extended")&&v.stopCoverage!=="all-planned-hours")errors.push("Stop coverage does not include planned holding/trading hours");
   const q=v.quantity,grossRisk=q*(v.entry-v.stop),grossReward=q*(v.target1-v.entry);
   const fees=v.entryFee+v.exitFee;
   const slippage=q*v.roundTripSlipPerShare;
   const costs=fees+slippage;
   const netRisk=grossRisk+costs,netReward=grossReward-costs;
   const rr=netRisk>0?netReward/netRisk:NaN;
   const notional=q*v.entry+v.entryFee+q*v.roundTripSlipPerShare/2;
   if(notional>v.cashUSD+1e-7)errors.push("Purchased shares exceed the entered cash budget");
   if(netRisk>v.maxLossUSD+1e-7)errors.push("Estimated loss exceeds the per-trade loss budget");
   if(netReward<=0)errors.push("First-target reward is eliminated by costs");
   if(!Number.isFinite(rr)||rr<2-1e-7)errors.push("Net first-target R:R below the manual's 2.0 guideline");
   if(v.overnightHold&&v.stopCoverage!=="all-planned-hours")errors.push("Overnight hold lacks verified protection across intended hours");
   if(v.overnightHold&&!v.gapRiskAccepted)errors.push("Overnight gap risk has not been accepted");
   if(v.eventBeforeExit&&!v.eventRiskPlanVerified)errors.push("Scheduled binary event before exit lacks a documented exposure plan");
   if(v.setupType==="countertrend"&&!v.countertrendRiskAccepted)errors.push("Countertrend setup requires explicit higher-risk acknowledgement");
   for(const key of REQUIRED)if(v[key]!==true)pending.push(key);
   if(pending.length)errors.push("Required factual checklist not completed: "+pending.join(", "));
   return {status:errors.length?"BLOCKED":"CONDITIONALLY ELIGIBLE — MANUAL APPROVAL STILL REQUIRED",errors,pending,
       calculations:{grossRisk:+grossRisk.toFixed(2),grossReward:+grossReward.toFixed(2),
       fees:+fees.toFixed(2),roundTripSlip:+slippage.toFixed(2),netRisk:+netRisk.toFixed(2),netReward:+netReward.toFixed(2),
       netRR:Number.isFinite(rr)?+rr.toFixed(3):null,cashNeeded:+notional.toFixed(2),maxAffordableShares:Math.max(0,Math.floor((v.cashUSD-v.entryFee)/(v.entry+v.roundTripSlipPerShare/2))),
       sizeWithinRiskBudget:netRisk<=v.maxLossUSD+1e-7}};
 }
 const API={evaluate,REQUIRED};
 root.SwingExecutionGate=API;
 if(typeof module!=="undefined"&&module.exports)module.exports=API;
 })(typeof globalThis!=="undefined"?globalThis:this);
