/* Fail production if a dashboard contains duplicate scripts after </html>,
 * non-parsable inline JavaScript, or broken static relative assets. */
const fs=require("node:fs"),path=require("node:path"),assert=require("node:assert/strict");
const root=path.resolve(__dirname,"..");
const pages=["index.html","rrg.html","stock-leadership.html","sector-breadth.html","rotation-lab.html","sectors.html","industries.html","rates.html","equity.html","calendar.html","trade-gate.html"];
let totalScripts=0;
for(const file of pages){
 const html=fs.readFileSync(path.join(root,file),"utf8");
 const closes=[...html.matchAll(/<\/html\s*>/gi)];
 assert.equal(closes.length,1,file+" must have exactly one closing </html> tag");
 assert.equal(html.slice(closes[0].index+closes[0][0].length).trim(),"",file+" has dangling content AFTER closing </html> (ghost UI/duplicate JS)");
 assert.equal([...html.matchAll(/<\/body\s*>/gi)].length,1,file+" must have one closing body tag");
 assert.ok(html.includes("<head")&&html.includes("<body"),file+" has no document structure");
 for(const match of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi)){
   const attrs=match[1],code=match[2].trim();
   if(/\bsrc\s*=/.test(attrs))continue;
   if(!code)continue;
   try{new Function(code)}catch(err){throw Error(file+" has malformed inline script: "+err.message)}
   totalScripts++;
 }
 for(const match of html.matchAll(/(?:src|href)="([^"]+\.(?:js|css))"/g)){
   if(/^https?:\/\//.test(match[1]))continue;
   const resource=match[1].split("?")[0];
   if(!fs.existsSync(path.join(root,resource)))throw Error(file+" references missing static asset "+resource);
 }
}
assert.ok(totalScripts>6,"Scripts apparently missing from dashboard files");
const stock=fs.readFileSync(path.join(root,"stock-leadership.html"),"utf8");
assert.ok(stock.includes("fetchJson('data/rrg-core.json')"),"Stock radar lacks robust core feed loading");
assert.ok(stock.includes("StockLeadership.rank"),"Stock radar has no ranking action");
assert.ok(stock.includes("NO VALID SIGNAL"),"Stock radar must fail closed with readable error");
const rrg=fs.readFileSync(path.join(root,"rrg.html"),"utf8");
assert.ok(rrg.includes('BAR AS-OF')&&rrg.includes('reference-trajectory-audit.json'),"RRG chart does not label actual trading sessions/reference comparison");
console.log("HTML/INLINE JS AUDIT PASSED: "+pages.length+" dashboards, "+totalScripts+" scripts; no trailing corruption or missing local CSS/JS");
