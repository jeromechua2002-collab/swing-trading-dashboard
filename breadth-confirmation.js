/* Transparent interpretation of the cap/equal-weight lesson. Experimental,
   relative context only; never an execution or win-probability model. */
(function(root){
const NEAR_LINE=0.35;
function rotation(trail){
 if(!Array.isArray(trail)||trail.length<4)throw Error('Four RRG points are required');
 const a=trail.slice(-4),h=a.at(-1),first=a[0];
 if(a.some(p=>!Number.isFinite(p.ratio)||!Number.isFinite(p.momentum)))throw Error('Invalid RRG values');
 const dx=(h.ratio-first.ratio)/3,dy=(h.momentum-first.momentum)/3,noise=.015;
 const direction=dx>noise&&dy>noise?'improving':dx < -noise&&dy < -noise?'deteriorating':'mixed';
 const quadrant=h.ratio>=100?(h.momentum>=100?'Leading':'Weakening'):(h.momentum>=100?'Improving':'Lagging');
 // Same boundary rule as the RRG page: heads within NEAR_LINE of a centre line are flagged, not hidden.
 const quad=(x,y)=>x>=100?(y>=100?'Leading':'Weakening'):(y>=100?'Improving':'Lagging'),nx=Math.abs(h.ratio-100)<NEAR_LINE,ny=Math.abs(h.momentum-100)<NEAR_LINE;
 const alt=nx||ny?quad(nx?(h.ratio>=100?99:101):h.ratio,ny?(h.momentum>=100?99:101):h.momentum):quadrant,near=alt===quadrant?'':alt;
 const phase=direction==='improving'?(quadrant==='Improving'?'Recovery gaining strength':quadrant==='Leading'?'Leader extending':quadrant==='Lagging'?'Early turn inside Lagging':'Momentum rebuilding'):
 direction==='deteriorating'?(quadrant==='Weakening'?'Leader fading toward Lagging':quadrant==='Lagging'?'Weakness extending':'Early deterioration'):'Tail directions disagree or are near flat';
 return {direction,quadrant,near,phase,dx,dy,head:h};
}
function confirmation(d,cap,thesis='long',lens='video',scope='sector',window='20'){
 const r=d.rows.find(r=>r.cap===cap);if(!r)throw Error('Sector pair missing');
 if(!['long','short'].includes(thesis))throw Error('Invalid underlying thesis');
 const ewKey=lens==='common'?'equal_vs_SPY':'equal_vs_RSP';
 const c=rotation(d.rrg.cap_vs_SPY[cap]),e=rotation(d.rrg[ewKey][r.equal]);
 const wanted=thesis==='long'?'improving':'deteriorating',opposite=thesis==='long'?'deteriorating':'improving';
 const capAgree=c.direction===wanted,ewAgree=e.direction===wanted;
 let label,read,tone;
 if(capAgree&&ewAgree){label='Both rotations support your '+thesis+' thesis';tone='support';read=thesis==='long'?'Strength is improving in the cap-weight and equal-weight sector views. This adds broad sector confirmation.':'Weakness is extending in the cap-weight and equal-weight sector views. This adds broad sector confirmation.';}
 else if(c.direction===opposite&&e.direction===opposite){label='Both rotations oppose your '+thesis+' thesis';tone='conflict';read='Both sector views rotate against the proposed underlying direction. Treat this as conflicting context, then inspect whether your own setup has independent strength.';}
 else if(capAgree){label='Partial support — the broader sector has not confirmed';tone='partial';read=thesis==='long'?'Cap-weight rotation improves, but equal weight does not confirm it. The strongest large companies may still work; a broad-sector claim needs more evidence.':'Cap-weight rotation deteriorates, but equal weight does not confirm it. Weakness may be concentrated in heavyweight companies.';}
 else if(ewAgree){label='Equal weight moves first — cap weight has not confirmed';tone='partial';read=thesis==='long'?'Broader participation improves before the cap-weight sector. Look for emerging industry or stock leaders; the cap-weight recovery is still unconfirmed.':'Broader participation deteriorates before the cap-weight sector. Large names may still support the index; check your actual underlying for a breakdown.';}
 else{label='Mixed — no clear sector confirmation';tone='mixed';read='Flat or opposing tails do not give a clear answer. Keep the rotation disagreement visible and let the industry and absolute-price chart resolve the setup.';}
 const prices=d.prices[cap],n=Number(window);if(!prices||prices.length<=n)throw Error('Price history missing');
 const absolute=100*(prices.at(-1).close/prices.at(-n-1).close-1);
 const m=r.metrics[String(window)],spread=m.equal_vs_cap;
 const participation=spread>.25?'Equal weight is outperforming cap weight':spread<-.25?'Cap weight is outperforming equal weight':'Neither weighting has a clear return advantage';
 const caveat=scope==='industry'?'This is broad-sector context. It does not directly confirm an industry ETF: inspect that industry’s RRG and own chart.':scope==='stock'?'This is broad-sector context. A single stock can differ from its sector: inspect that stock’s relative strength and own chart.':'This directly compares the two sector ETF proxies. Confirm the traded ETF’s own price setup next.';
 const priceNote=(thesis==='long'&&absolute<0)||(thesis==='short'&&absolute>0)?'Relative rotation and the selected-window price direction disagree. Check the recent 4H base or trend; a relative signal alone does not establish the trade direction.':'The selected-window price move is compatible with the thesis, but it does not establish a current 4H/entry trigger.';
 return {row:r,cap:c,equal:e,label,tone,read,participation,absolute,spread,priceNote,caveat,
 next:thesis==='long'?'Check the industry/stock leader, then the 4H recovery or continuation and your 1H/15–30m entry trigger.':'Check the industry/stock weakness, then the 4H failed rally or breakdown and your 1H/15–30m entry trigger.',
 benchmarkText:lens==='common'?'Both RRG views use SPY. This is the shared-benchmark diagnostic.':'Video lens: cap-weight / SPY and equal-weight / RSP. Compare direction and quadrant; do not subtract coordinates.'};
}
root.breadthRotation=rotation;root.breadthConfirmation=confirmation;
if(typeof module!=='undefined')module.exports={rotation,confirmation};
})(typeof globalThis!=='undefined'?globalThis:this);
