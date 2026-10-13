/* Static GitHub Pages release health — no guessed 'live' status or prices. */
(function(root){
 "use strict";
 const date=v=>{const x=Date.parse(v);if(!Number.isFinite(x))throw Error("Missing or invalid source timestamp");return x};
 function validate(manifest,rrg,breadth,journal,digests,now=Date.now()){
   if(manifest?.schema_version!==1||manifest.market_status!=="validated_completed_session")throw Error("Missing validated release manifest");
   if(!rrg?.universes?.stock_members||!rrg?.timeframes?.["1D"]?.benchmark_price?.length)throw Error("Incomplete RRG dataset");
   const sectors=rrg.universes.stock_members, names=Object.keys(sectors);
   const count=Object.values(sectors).flat().length;
   if(names.length!==11||count!==116||new Set(Object.values(sectors).flat()).size!==116)throw Error("Missing or duplicate RRG stock members");
   const session=rrg.timeframes["1D"].benchmark_price.at(-1).time.slice(0,10);
   if(session!==manifest.rrg_session||session!==manifest.breadth_session||session!==breadth?.as_of)throw Error("RRG/breadth trading sessions disagree");
   if(breadth?.status!=="ok"||breadth?.rows?.length!==11||new Set(breadth.rows.map(x=>x.cap)).size!==11||names.some(n=>!breadth.rows.some(x=>x.cap===n)))throw Error("Sector breadth pairs incomplete");
   if(manifest.market_generated_at!==rrg.generated_at||!manifest.journal_generated_at||manifest.journal_generated_at!==journal.updated_at)throw Error("Release/data generation times differ");
   if(manifest.market_coverage?.stocks!==116||manifest.market_coverage?.industries!==16||manifest.market_coverage?.breadth_pairs!==11||manifest.market_coverage?.timeframes!==4)throw Error("Manifest declares incomplete market coverage");
   if(!Array.isArray(journal?.closed_trades)||!Array.isArray(journal?.open_trades)||!journal.curve?.length)throw Error("Journal missing");
   if(journal.closed_trades.length!==manifest.journal_closed_count||journal.open_trades.length!==manifest.journal_open_count||Math.abs(journal.current_equity_sgd-manifest.journal_equity_sgd)>0.005||Math.abs(journal.curve.at(-1).equity_sgd-journal.current_equity_sgd)>0.005)throw Error("Journal curve/manifest mismatch");
   if(!["manual_snapshot","notion_sync"].includes(manifest.journal_status))throw Error("Unknown journal sync provenance");
   for(const [k,v] of Object.entries(manifest.sha256||{})){
     if(!/^[0-9a-f]{64}$/.test(v)||digests?.[k]!==v)throw Error("Release integrity hash mismatch for "+k);
   }
   if(["rrg","breadth","journal"].some(k=>!manifest.sha256?.[k]))throw Error("Release lacks dataset fingerprints");
   const ageHours=(now-date(manifest.market_generated_at))/3600000;
   const journalAge=(now-date(journal.updated_at))/3600000;
   if(ageHours < -1||journalAge < -1)throw Error("Future feed generation time");
   const staleMarket=ageHours>96;
   const journalLabel=manifest.journal_status==="manual_snapshot"?"Verified manual snapshot":journalAge>72?"Notion snapshot overdue":"Notion journal sync";
   return {
     market:staleMarket?"Old completed-session data":"Completed-session data validated",
     marketHealthy:!staleMarket,
     journal:journalLabel,
     journalLive:manifest.journal_status==="notion_sync"&&journalAge<=72,
     session,
     stocks:count,
     sectors:names.length,
     industries:16,
     equity:journal.current_equity_sgd,
     realized:journal.realized_pnl_sgd,
     closed:journal.closed_trades.length,
     open:journal.open_trades.length,
     marketGenerated:manifest.market_generated_at,
     journalGenerated:journal.updated_at,
     lastClosed:manifest.journal_last_closed_trade,
     workflowRun:manifest.workflow_run,
     commit:manifest.commit,
     marketAgeHours:ageHours,
     journalAgeHours:journalAge
   };
 }
 const api={validate};
 root.TradingDeskHealth=api;
 if(typeof module!=="undefined"&&module.exports)module.exports=api;
 })(typeof globalThis!=="undefined"?globalThis:this);
