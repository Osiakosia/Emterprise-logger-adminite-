let AUTO=null,BILL=null,STOP=false;
const qs=(id)=>document.getElementById(id);
const setBadge=(el,cls,txt)=>{if(!el)return;el.className=cls;el.textContent=txt;};

async function apiStatus(){const r=await fetch("/api/status",{cache:"no-store"});if(!r.ok)throw new Error("status");return await r.json();}
async function apiSend(dest,header,dataHex){
  const body={dest:Number(dest),header:Number(header),data_hex:(dataHex||"").trim()};
  const r=await fetch("/api/send",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  const j=await r.json().catch(()=>({}));if(!r.ok||j.ok===false)throw new Error(j.error||"send");return j;
}

function selAddr(){
  const t=(qs("selAddr")?.textContent||"").trim();
  const n=Number(t);
  if(!Number.isFinite(n) || n<0 || n>255) return null;
  return n;
}
function requireAddr(){
  const a=selAddr();
  if(a===null){
    alert("Select a device on the left first (address must be a number).");
    return null;
  }
  return a;
}

function health(dev){const now=Date.now()/1000,last=dev?.last_seen_ts||0,d=now-last;return d<2?"online":d<5?"slow":"offline";}
function updateConn(st){const ok=!!(st.serial?st.serial.connected:st.connected);
setBadge(qs("connBadge"),ok?"badge badge-success badge-pill":"badge badge-secondary badge-pill",ok?"CONNECTED":"DISCONNECTED");
qs("portLabel").textContent=(st.serial?st.serial.port:st.port)||"-";qs("baudLabel").textContent=(st.serial?st.serial.baud:st.baud)||"-";}
function updateHealth(dev){const b=qs("healthBadge");if(!b){return;}if(!dev){setBadge(b,"badge badge-secondary badge-pill","UNKNOWN");return;}
const h=dev.health||health(dev);setBadge(b,h==="online"?"badge badge-success badge-pill":h==="slow"?"badge badge-warning badge-pill":"badge badge-danger badge-pill",
h==="online"?"ONLINE":h==="slow"?"SLOW":"OFFLINE");}
function dispName(d){const p=[];if(d.name)p.push(d.name);if(d.manufacturer)p.push(d.manufacturer);if(d.product)p.push(d.product);return p.filter(Boolean).join(" • ")||`Device ${d.addr}`;}
function meta(d){const b=[];if(d.kind)b.push(d.kind);if(d.equipment_category!==undefined)b.push(`cat:${d.equipment_category}`);if(d.last_seen)b.push(`seen:${d.last_seen}`);return b.join(" | ")||"—";}
function renderDevices(devs){const box=qs("deviceList");if(!box)return;
const q=(qs("deviceSearch")?.value||"").toLowerCase().trim();const addrs=Object.keys(devs||{}).sort((a,b)=>Number(a)-Number(b));
const rows=[];for(const a of addrs){const d=devs[a];const label=`${a} ${dispName(d)} ${meta(d)}`.toLowerCase();if(q&&!label.includes(q))continue;
const h=d.health||health(d);const dot=h==="online"?"bg-success":h==="slow"?"bg-warning":"bg-danger";
rows.push(`<div class="d-flex align-items-center p-2 border rounded mb-1 device-row" data-addr="${a}" style="cursor:pointer;">
<span class="badge badge-dark mr-2">${a}</span><span class="${dot} mr-2" style="width:10px;height:10px;border-radius:50%;display:inline-block;"></span>
<div><div class="font-weight-bold" style="line-height:1.1">${dispName(d)}</div><div class="small text-muted" style="line-height:1.1">${meta(d)}</div></div></div>`);}
box.innerHTML=rows.length?rows.join(""):`<div class="p-2 text-muted">No devices.</div>`;
box.querySelectorAll(".device-row").forEach(el=>el.addEventListener("click",()=>selectDevice(el.getAttribute("data-addr"),devs)));
qs("deviceCountBadge").textContent=String(addrs.length);}
function autoTab(d){if(!d)return;const cat=d.equipment_category,kind=(d.kind||"").toLowerCase();
if(kind==="coin"||cat===2)$("#tab-coin").tab("show");else if(kind==="hopper"||cat===6)$("#tab-hopper").tab("show");else if(kind==="bill"||kind==="recycler"||cat===1)$("#tab-recycler").tab("show");}
function selectDevice(addr,devs){addr=String(addr);const d=(devs||{})[addr];
qs("selAddr").textContent=addr;qs("selAddrBadge").textContent=addr;qs("selName").textContent=d?dispName(d):`Address ${addr}`;qs("selMeta").textContent=d?meta(d):"—";
updateHealth(d);autoTab(d);}
function renderFrames(frames){const tb=qs("controllerFramesTbody");if(!tb)return;const last=(frames||[]).slice(-12).reverse();
tb.innerHTML=last.map(f=>`<tr><td>${f.time||""}</td><td><span class="badge ${String(f.direction).toUpperCase()==="RX"?"badge-success":"badge-primary"}">${f.direction}</span></td>
<td>${f.from??""}</td><td>${f.to??""}</td><td><code>${f.hex||f.raw_hex||""}</code></td><td>${f.decoded||""}</td></tr>`).join("");}
function bindHeaderBtns(){document.querySelectorAll("[data-header]").forEach(btn=>btn.addEventListener("click",async()=>{
const addr=requireAddr(); if(addr===null) return;
try{const h=btn.getAttribute("data-header");const hex=btn.getAttribute("data-hex")||"";
await apiSend(addr,h,hex);if(qs("cmdResult"))qs("cmdResult").textContent="Sent.";}
catch(e){if(qs("cmdResult"))qs("cmdResult").textContent="ERROR: "+e.message;}}));}
function hopperCoins(){const amt=Number(qs("hopperAmount")?.value||0);const el=qs("hopperCoins");if(!el)return 0;if(amt%2!==0){el.value=0;return 0;}const c=amt/2;el.value=c;return c;}
function bindHopper(){qs("hopperAmount")?.addEventListener("input",hopperCoins);
document.querySelectorAll("[data-quick-eur]").forEach(b=>b.addEventListener("click",()=>{qs("hopperAmount").value=b.getAttribute("data-quick-eur");hopperCoins();}));
qs("btnHopperEnable")?.addEventListener("click",async()=>{const addr=requireAddr(); if(addr===null) return; await apiSend(addr,164,"").catch(()=>{});});
qs("btnHopperStop")?.addEventListener("click",async()=>{const addr=requireAddr(); if(addr===null) return; await apiSend(addr,172,"").catch(()=>{});});
qs("btnHopperPay")?.addEventListener("click",async()=>{
const addr=requireAddr(); if(addr===null) return;
const c=hopperCoins();if(c<=0){alert("Amount must be multiple of €2");return;}
if(c>255){alert("Max 255 coins");return;}
await apiSend(addr,167,Number(c).toString(16).padStart(2,"0"));});hopperCoins();}
function bindRecycler(){
qs("btnEscrowStack")?.addEventListener("click",async()=>{const addr=requireAddr(); if(addr===null) return; await apiSend(addr,154,"01").catch(()=>{});});
qs("btnEscrowReturn")?.addEventListener("click",async()=>{const addr=requireAddr(); if(addr===null) return; await apiSend(addr,154,"00").catch(()=>{});});
qs("btnStartBillPoll")?.addEventListener("click",()=>{const addr=requireAddr(); if(addr===null) return; const ms=Math.max(200,Number(qs("billPollMs")?.value||250));
if(BILL)return;BILL=setInterval(()=>apiSend(addr,159,"").catch(()=>{}),ms);});
qs("btnStopBillPoll")?.addEventListener("click",()=>{clearInterval(BILL);BILL=null;});}
function bindCustom(){qs("btnSendCustom")?.addEventListener("click",async()=>{
const addr=requireAddr(); if(addr===null) return;
try{const h=Number(qs("customHeader")?.value||0);const data=(qs("customData")?.value||"").trim();await apiSend(addr,h,data);qs("cmdResult").textContent="Sent.";}
catch(e){qs("cmdResult").textContent="ERROR: "+e.message;}});}
async function scan(){STOP=false;const s=Number(qs("scanStart")?.value||1),e=Number(qs("scanEnd")?.value||50),d=Number(qs("scanDelay")?.value||80);
qs("scanStatus").textContent="Scanning…";for(let a=s;a<=e;a++){if(STOP)break;try{await apiSend(a,254,"");}catch(_){}
qs("scanStatus").textContent=`Scan ${a}/${e}`;if(d)await new Promise(r=>setTimeout(r,d));}qs("scanStatus").textContent=STOP?"Stopped":"Done";}
function bindScan(){qs("btnScan")?.addEventListener("click",scan);qs("btnStopScan")?.addEventListener("click",()=>{STOP=true;});}
async function refresh(){const st=await apiStatus();updateConn(st);renderDevices(st.devices||{});renderFrames(st.frames||[]);
const sel=qs("selAddr")?.textContent?.trim();if(sel&&(st.devices||{})[sel])updateHealth((st.devices||{})[sel]);}
function startAuto(){if(AUTO)return;AUTO=setInterval(()=>refresh().catch(()=>{}),1000);}
function stopAuto(){clearInterval(AUTO);AUTO=null;}
function init(){bindHeaderBtns();bindHopper();bindRecycler();bindCustom();bindScan();
qs("btnRefreshDevices")?.addEventListener("click",()=>refresh().catch(()=>{}));
qs("deviceSearch")?.addEventListener("input",()=>refresh().catch(()=>{}));
qs("autoRefreshSwitch")?.addEventListener("change",function(){this.checked?startAuto():stopAuto();});
refresh().catch(()=>{});startAuto();}
document.addEventListener("DOMContentLoaded",init);
