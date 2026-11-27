// 判定のテスト：時計をずらして、日付の変わり目・発売時刻の前後・更新前を確かめる
const {chromium}=require('playwright');
const cases=[["2026-11-28T05:59:00Z","11/28 14:59"],["2026-11-28T06:01:00Z","11/28 15:01"],["2026-11-28T15:01:00Z","11/29 0:01（日付が変わった直後）"],["2026-11-30T23:59:00Z","12/1 8:59（Cloudberry発売直前）"],["2026-12-01T00:01:00Z","12/1 9:01（Cloudberry発売直後）"]];
(async()=>{const b=await chromium.launch();
for (const w of [390,1280]) for (const [iso,label] of cases){
const p=await b.newPage({viewport:{width:w,height:900}});const errs=[];p.on('pageerror',e=>errs.push(e.message));
await p.addInitScript(t=>{const off=new Date(t).getTime()-Date.now();const N=Date.now;Date.now=()=>N()+off;},iso);
await p.goto('http://localhost:8765/');await p.waitForTimeout(4000);
const r=await p.evaluate(()=>({today:TODAY,
 doneButUp:DATA.filter(g=>!released(g)&&g.versions.some(v=>v.raw.sd&&(v.raw.d+" "+(v.raw.rt||"00:00"))<=NOW_JST()&&v.raw.pr!=null)).map(g=>g.t),
 relNoPrice:DATA.filter(g=>released(g)&&g.d>=APP_WAIT&&!g.versions.some(v=>v.raw.pr!=null||v.raw.gp.length)).map(g=>g.t),
 cloud:DATA.filter(g=>/Cloudberry/.test(g.t)).map(g=>released(g)?"発売中":"発売予定")[0]}));
console.log(w,label,errs.length?errs:"",JSON.stringify(r));await p.close();}
await b.close();})();
