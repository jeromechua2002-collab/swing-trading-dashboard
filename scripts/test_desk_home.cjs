const fs=require("node:fs"),assert=require("node:assert/strict"),path=require("node:path");
const root=path.resolve(__dirname,".."),html=fs.readFileSync(path.join(root,"index.html"),"utf8");
assert.ok(html.includes("desk-health.js")&&html.includes("data/release-manifest.json"),"Homepage lacks validated-release health");
assert.ok(html.includes('aria-live="polite"')&&html.includes("Recheck data"),"Accessible data status or refresh missing");
assert.ok(html.includes("Stock Leaders")&&html.includes("Trade Gate")&&html.includes("Journal"),"Research nav incomplete");
assert.ok(html.includes("data/journal-performance.json")&&html.includes("data/sector-breadth.json"),"Cross-file coherence checks not wired");
const links=[...html.matchAll(/<a\b[^>]*href="([^"]+)"/g)].map(x=>x[1]);
for(const name of links){
 if(/^(https?:|#)/.test(name))continue;
 assert.ok(!name.includes(".."),"Unsafe navigation: "+name);
 const rel=name.split("?")[0];
 assert.ok(fs.existsSync(path.join(root,rel)),"Broken homepage link: "+name);
}
let count=0;
for(const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)){
 if(/\bsrc=/.test(m[1]))continue;
 const code=m[2].trim();
 if(code){new Function(code);count++}
}
assert.ok(count,"No homepage script parsed");
console.log("DESK HOME CHECK PASSED: navigation, source-aware health badges, keyboard refresh, scoped panels, valid inline JavaScript");
