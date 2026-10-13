/* Stock-level leadership discovery from the existing, versioned RRG universe.
   Classification is RELATIVE, not a trading signal; benchmarks always explicit. */
(function(root){
"use strict";
const tfNames=["1D","4H"];
function quadrant(p){
 if(!p||!Number.isFinite(p.ratio)||!Number.isFinite(p.momentum))throw Error("Non-finite RRG coordinate");
 return p.ratio>=100?(p.momentum>=100?"Leading":"Weakening"):(p.momentum>=100?"Improving":"Lagging");
}
function compare(trail){
 if(!Array.isArray(trail)||trail.length!==16)throw Error("Incomplete RRG trail (16 observations required)");
 const dates=trail.map(v=>v.time);
 if(dates.some((v,i)=>typeof v!=="string"||i>0&&v<=dates[i-1]))throw Error("RRG dates are invalid or not increasing");
 trail.forEach(quadrant);
 const head=trail[15],base=trail[10];
 return {q:quadrant(head),ratio:head.ratio,mom:head.momentum,dr:+(head.ratio-base.ratio).toFixed(3),dm:+(head.momentum-base.momentum).toFixed(3),date:head.time.slice(0,10)};
}
function phase(d,h){
 if(d.q==="Leading"&&h.q==="Leading")return "Leader / 4H confirming";
 if(d.q==="Leading"&&h.q==="Weakening")return "Leader cooling on 4H";
 if(d.q==="Improving"&&h.q==="Improving")return "Early rotation / 4H aligned";
 if(d.q==="Improving"&&h.q==="Lagging")return "Daily recovery / 4H unconfirmed";
 if(d.q==="Lagging"&&h.q==="Leading")return "4H bounce / daily laggard";
 if(d.q==="Lagging"&&h.q==="Improving")return "4H turn / daily laggard";
 if(d.q==="Weakening")return "Daily leader losing momentum";
 if(d.q==="Lagging")return "Relative laggard";
 return "Mixed / monitor";
}
function rank(core,file,sector,now=Date.now()){
 const members=core?.universes?.stock_members?.[sector];
 if(!Array.isArray(members)||!members.length||!Array.isArray(file?.members)||JSON.stringify(members)!==JSON.stringify(file.members)||file.sector!==sector)throw Error("Stock membership mismatch: "+sector);
 if(file.generated_at!==core.generated_at)throw Error("Stock/core snapshot generation mismatch");
 const stamp=Date.parse(file.generated_at);
 if(!Number.isFinite(stamp)||stamp>now+300000)throw Error("Invalid stock snapshot timestamp");
 const out=[];
 const expected={};
 for(const tf of tfNames){
   if(!core.timeframes?.[tf]?.benchmark_price?.length)throw Error("Missing market benchmark "+tf);
   expected[tf]=core.timeframes[tf].benchmark_price.at(-1).time.slice(0,10);
 }
 for(const ticker of members){
   if(!/^[A-Z0-9.-]{1,10}$/.test(ticker))throw Error("Unsafe ticker");
   const row={ticker};
   for(const tf of tfNames){
     const node=file?.timeframes?.[tf]?.stock;
     if(!node)throw Error(ticker+" missing "+tf);
     for(const [basis,key] of [["sector","vs_"+sector],["spy","vs_SPY"]]){
       const series=node?.[key]?.[ticker];
       const head=compare(series);
       if(head.date!==expected[tf])throw Error(ticker+" "+tf+" "+key+" differs from market benchmark session "+expected[tf]);
       row[tf+"_"+basis]=head;
     }
   }
   row.phase=phase(row["1D_sector"],row["4H_sector"]);
   out.push(row);
 }
 if(new Set(out.map(x=>x.ticker)).size!==members.length)throw Error("Duplicate ticker in "+sector);
 out.sort((a,b)=>b["1D_sector"].ratio-a["1D_sector"].ratio||b["1D_sector"].mom-a["1D_sector"].mom||a.ticker.localeCompare(b.ticker));
 const currentDate=expected["1D"];
 const age=(now-Date.parse(currentDate+"T23:59:59Z"))/86400000;
 if(age>7)throw Error("Stock session is stale: "+currentDate);
 if(age < -2)throw Error("Future stock session");
 return {sector,rows:out,session:currentDate,generated_at:file.generated_at,latest_4h:expected["4H"],stale:age>3,age_days:Math.max(0,Math.round(age*10)/10)};
}
root.StockLeadership={quadrant,compare,phase,rank};
if(typeof module!=="undefined"&&module.exports)module.exports=root.StockLeadership;
})(typeof globalThis!=="undefined"?globalThis:this);
