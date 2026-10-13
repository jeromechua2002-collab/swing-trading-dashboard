/* Shared fail-closed guard for the experimental equal-weight views. */
(function(root){
  const pairs={XLK:'RSPT',XLY:'RSPD',XLC:'RSPC',XLU:'RSPU',XLRE:'RSPR',XLP:'RSPS',XLI:'RSPN',XLB:'RSPM',XLF:'RSPF',XLV:'RSPH',XLE:'RSPG'};
  const states=new Set(['Broad leadership','Heavyweight-led','Broadening under the surface','Broad weakness','Mixed / transition']);
  const quads=new Set(['Leading','Weakening','Improving','Lagging']);
  function validateBreadthFeed(d,now=Date.now()){
    if(!d||d.status!=='ok'||!Array.isArray(d.rows)||d.rows.length!==11)throw Error('Comparison feed is unavailable or incomplete');
    for(const key of ['generated_at','source_generated_at']){
      const age=now-Date.parse(d[key]);
      if(!Number.isFinite(age)||age < -300000||age>72*3600000)throw Error('Invalid or stale '+key);
    }
    if(typeof d.as_of!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(d.as_of))throw Error('Invalid session date');
    const session=Date.parse(d.as_of+'T00:00:00Z');
    if(!Number.isFinite(session)||session>now||now-session>5*86400000)throw Error('Invalid or stale session');
    const seen=new Set();
    for(const r of d.rows){
      if(!r||pairs[r.cap]!==r.equal||seen.has(r.cap))throw Error('Duplicate or mismatched sector pair');
      seen.add(r.cap);
      if(![r.cap_quadrant,r.equal_quadrant,r.equal_rsp_quadrant].every(q=>quads.has(q)))throw Error('Invalid RRG quadrant');
      for(const n of ['5','10','20','60']){
        const m=(r.metrics||{})[n];
        if(!m||!states.has(m.state)||!['cap_vs_spy','equal_vs_spy','equal_vs_cap','equal_vs_rsp','ratio_slope_5d'].every(k=>Number.isFinite(m[k])))throw Error('Invalid comparison metrics');
      }
      for(const [key,t] of [['cap_vs_SPY',r.cap],['equal_vs_SPY',r.equal],['equal_vs_RSP',r.equal]]){
        const trail=((d.rrg||{})[key]||{})[t];
        if(!Array.isArray(trail)||trail.length!==16||trail.at(-1).time.slice(0,10)!==d.as_of||trail.some(p=>!Number.isFinite(p.ratio)||!Number.isFinite(p.momentum)))throw Error('Invalid or mismatched RRG trail');
      }
    }
    const reference=(d.prices||{}).SPY;
    if(!Array.isArray(reference)||reference.length<100)throw Error('SPY history missing');
    const sessions=reference.map(p=>p.time);
    if(new Set(sessions).size!==sessions.length||sessions.at(-1)!==d.as_of)throw Error('Duplicate or mismatched price sessions');
    for(const t of ['SPY','RSP',...Object.keys(pairs),...Object.values(pairs)]){
      const history=(d.prices||{})[t];
      if(!Array.isArray(history)||history.length!==sessions.length||history.some((p,i)=>p.time!==sessions[i]||!Number.isFinite(p.close)||p.close<=0))throw Error('Incomplete or invalid price history: '+t);
    }
    return d;
  }
  root.validateBreadthFeed=validateBreadthFeed;
  if(typeof module!=='undefined')module.exports=validateBreadthFeed;
})(typeof globalThis!=='undefined'?globalThis:this);
