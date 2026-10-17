/* Hardware Tuning Studio v2 — profile editor; never executes GPU/CPU writes. */
'use strict';
window.SignalTuning=(()=>{
 const STORE='signaldeck.tuning.profiles.v2';
 const LEVELS=[['simple','Simple'],['lv1','Extended Lv.1'],['lv2','Extended Lv.2'],['lv3','Extended Lv.3'],['expert','Expert']];
 const DETAILS={
  power:'Batas daya GPU sebagai persentase rancangan. Lebih rendah biasanya membatasi daya, tetapi dapat mengurangi performa. Ini belum dikirim ke driver.',
  core:'Offset clock inti GPU. Nilai terlalu tinggi dapat menyebabkan crash, artefak, atau driver reset. Di sini hanya rancangan.',
  memory:'Offset clock VRAM. Stabilitas bergantung GPU dan driver; error memori tidak selalu terlihat langsung.',
  target:'Target suhu yang ingin dipertahankan. Bukan jaminan suhu GPU tetap pada nilai tersebut.',
  fan:'Persentase duty kipas manual (jika GPU mendukung). Laptop dan eGPU bisa tidak mengizinkan kontrol kipas melalui driver.',
  auto:'Jika diaktifkan, firmware/driver mengendalikan kipas. Opsi ini hanya disimpan dalam profil.',
  corecurve:'Kurva voltage/frequency untuk mengilustrasikan titik operasi inti GPU. Kurva editor di web bukan kurva resmi driver atau MSI Afterburner.',
  fancurve:'Kurva duty kipas terhadap suhu GPU. Titik pada temperatur lebih tinggi harus memiliki duty yang tidak lebih rendah.',
  cpupl1:'PL1 adalah batas daya CPU berkelanjutan (long-term). Dukungan dan rentangnya ditentukan BIOS/firmware.',
  cpupl2:'PL2 adalah batas daya CPU jangka pendek (burst). Menaikkannya dapat meningkatkan suhu dan beban VRM.',
  cpuuv:'Offset tegangan inti CPU negatif. Banyak laptop membatasi undervolting melalui BIOS, microcode atau Intel Undervolt Protection.',
  temp:'Target suhu GPU dalam °C. Tidak sama dengan thermal shutdown limit.',
  profile:'Profil disimpan dalam browser ini dan dapat diekspor menjadi JSON. Membuka aplikasi di browser/profil lain tidak otomatis memindahkan profil.',
  apply:'Eksekusi OC/UV dinonaktifkan: aplikasi belum memiliki adapter vendor yang telah diverifikasi dan mekanisme rollback driver/firmware.'
 };
 const INIT={power:85,core:0,memory:0,target:78,fan:45,auto:true,fanpoints:[25,35,48,68,85],corecurve:[1800,1950,2100,2250,2380],cpupl1:45,cpupl2:90,cpuuv:0};
 const BOUNDS={power:[50,100],core:[-150,150],memory:[-250,250],target:[60,90],fan:[20,100],cpupl1:[15,120],cpupl2:[25,180],cpuuv:[-100,0]};
 let dataset=read();let selected='';let level='simple';let draft=structuredClone(INIT);
 let loadedDevice='';let drag=null;let capabilities=null;
 const working={},undoHistory={};
 const gpuKey=g=>'gpu:'+(g.stable_id||g.id);
 function remember(){const stack=undoHistory[selected]||(undoHistory[selected]=[]);stack.push(structuredClone(draft));if(stack.length>50)stack.shift()}
 function normalized(source){
  const clean=structuredClone(INIT);
  for(const [key,bounds] of Object.entries(BOUNDS))if(Number.isFinite(source?.[key]))clean[key]=range(source[key],...bounds);
  clean.cpupl2=Math.max(clean.cpupl1,clean.cpupl2);
  clean.auto=source?.auto===undefined?true:source.auto===true;
  for(const key of ['fanpoints','corecurve'])if(Array.isArray(source?.[key])&&source[key].length===5){
   clean[key]=source[key].map(v=>range(v,key==='fanpoints'?20:1000,key==='fanpoints'?100:3000));
   for(let i=1;i<5;i++)clean[key][i]=Math.max(clean[key][i-1],clean[key][i]);
  }
  return clean;
 }
 const fmt=(x)=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const range=(v,min,max)=>Math.min(max,Math.max(min,Number.isFinite(+v)?+v:min));
 function read(){try{const obj=JSON.parse(localStorage.getItem(STORE)||'{}');return obj&&typeof obj==='object'&&!Array.isArray(obj)?obj:{}}catch{return {}}}
 function persist(){localStorage.setItem(STORE,JSON.stringify(dataset))}
 function deviceKey(snapshot){const g=snapshot?.gpus||[];const options=[{id:'cpu',name:snapshot?.cpu?.name||'Processor (CPU)'}].concat(g.map(x=>({id:gpuKey(x),name:x.name})));
  if(!options.some(x=>x.id===selected))selected=g.length?gpuKey(g.find(x=>x.vendor?.toLowerCase().includes('nvidia'))||g[0]):'cpu';
  // Legacy index profiles remain stored. Do not silently assign them to a new UUID after hotplug.
  return options;
 }
 function load(){draft=normalized(working[selected]||dataset[selected]);loadedDevice=selected}
 function field(k,label,min,max,step,unit,tip){return `<div class="tune-field" data-help="${tip}"><div class="tune-field-title"><label for="tune-${k}">${fmt(label)} <span class="tune-help" data-tip="${tip}" tabindex="0" role="button" aria-label="Penjelasan ${fmt(label)}">?</span></label><output id="out-${k}">${fmt(draft[k])}${unit}</output></div><input id="tune-${k}" type="range" data-tune="${k}" min="${min}" max="${max}" step="${step}" value="${range(draft[k],min,max)}" aria-label="${fmt(label)}"><div class="range-limits"><span>${min}${unit}</span><span>${max}${unit}</span></div></div>`}
 function graph(values,tags,max,min=0){const key=max===100?'fanpoints':'corecurve';const W=640,H=215,P=25,den=Math.max(1,values.length-1);const xy=values.map((v,i)=>[P+i*(W-2*P)/den,H-P-(v-min)/(max-min)*(H-2*P)]);
  const path=xy.map((v,i)=>(i?'L':'M')+v[0].toFixed(1)+' '+v[1].toFixed(1)).join(' ');
  const grid=[0,.25,.5,.75,1].map(t=>`<line x1="${P}" y1="${P+(H-2*P)*t}" x2="${W-P}" y2="${P+(H-2*P)*t}" stroke="currentColor" opacity=".09"/>`).join('');
  return `<svg class="tune-chart-svg" viewBox="0 0 ${W} ${H}" aria-label="Grafik kurva interaktif">${grid}<path d="${path}" stroke="#8adbb7" stroke-width="3" fill="none" stroke-linejoin="round" stroke-linecap="round"/>${xy.map(([x,y],i)=>`<circle id="curve-${key}-${i}" data-curve="${key}" data-point="${i}" tabindex="0" role="slider" aria-label="${key==='fanpoints'?'Fan duty':'Frekuensi'} pada ${tags[i]} ${key==='fanpoints'?'Celsius':'mV'}" aria-valuemin="${key==='fanpoints'?20:min}" aria-valuemax="${max}" aria-valuenow="${values[i]}" cx="${x}" cy="${y}" r="9" fill="#a4eccc" stroke="#18352f" stroke-width="3"><title>${fmt(tags[i])} — ${values[i]} · drag atau tombol panah</title></circle><text x="${x}" y="${H-3}" text-anchor="middle" font-size="13" fill="currentColor">${fmt(tags[i])}</text>`).join('')}</svg>`;
 }
 function curvePanel(){const temps=[35,45,55,70,85];return `<div class="tune-panel"><div class="tune-panel-heading"><div><h3>Fan curve editor</h3><p>Tarik titik grafik atau gunakan tombol panah. Duty harus naik bersama suhu.</p></div><span class="tune-chip">PREVIEW</span></div><div id="tune-curve-chart">${graph(draft.fanpoints,temps,100)}</div><div class="tune-five">${temps.map((t,i)=>`<label class="tune-point"><span>${t}°C</span><input aria-label="Fan duty pada ${t} Celsius" type="range" data-fan-index="${i}" value="${draft.fanpoints[i]}" min="20" max="100" step="1"><b id="fan-${i}">${draft.fanpoints[i]}%</b></label>`).join('')}</div></div>`}
 function voltagePanel(){const mv=[750,800,850,900,950];return `<div class="tune-panel"><div class="tune-panel-heading"><div><h3>Voltage / frequency curve</h3><p>Tarik titik atau gunakan tombol panah · kurva rancangan, bukan pembacaan driver</p></div><span class="tune-chip">EXPERT PREVIEW</span></div><div id="tune-vf-chart">${graph(draft.corecurve,mv,3000,1000)}</div><div class="tune-five">${mv.map((t,i)=>`<label class="tune-point"><span>${t} mV</span><input aria-label="Frekuensi rancangan pada ${t} mV" type="range" data-vf-index="${i}" value="${draft.corecurve[i]}" min="1000" max="3000" step="10"><b id="vf-${i}">${draft.corecurve[i]} MHz</b></label>`).join('')}</div></div>`}
 function section(id,name,sub,body){return `<section class="tune-panel" id="${id}"><div class="tune-panel-heading"><div><h3>${name}</h3><p>${sub}</p></div></div>${body}</section>`}
 function output(snapshot){const devs=deviceKey(snapshot);const isCpu=selected==='cpu';const gpu=snapshot?.gpus?.find(x=>gpuKey(x)===selected),cpu=snapshot?.cpu;
  const utilization=isCpu?cpu?.usage_percent:gpu?.usage_percent,temperature=isCpu?cpu?.temperature_c:gpu?.temperature_c,power=isCpu?cpu?.power_w:gpu?.power_w;
  const staticWarning='RANCANGAN SAJA · BELUM MENGUBAH PERANGKAT';
  let control=isCpu?section('base','CPU basic planning','Parameter CPU ditentukan BIOS/firmware. Tuning fisik belum didukung.',field('cpupl1','CPU PL1 power limit',15,120,1,' W','cpupl1')):section('base','GPU essentials','Pengaturan ala Afterburner, tanpa menulis ke driver.',field('power','GPU power target',50,100,1,' %','power')+field('core','Core clock offset',-150,150,5,' MHz','core'));
  if(level!=='simple')control+=isCpu?section('ext1','Extended Level 1','Tuning CPU baseline',field('cpupl2','CPU PL2 boost limit',25,180,1,' W','cpupl2')):section('ext1','Extended Level 1','GPU clocks & target suhu',field('memory','Memory clock offset',-250,250,5,' MHz','memory')+field('target','Temperature target',60,90,1,'°C','target'));
  if(['lv2','lv3','expert'].includes(level))control+=isCpu?section('ext2','Extended Level 2','Undervolt CPU — input simulasi, BIOS mungkin terkunci',field('cpuuv','CPU voltage offset',-100,0,5,' mV','cpuuv')):section('ext2','Extended Level 2','Fan control concepts',`<div class="tune-inline"><span>Fan control mode <span class="tune-help" data-tip="auto" tabindex="0">?</span></span><label class="tune-check"><input type="checkbox" id="tune-auto" ${draft.auto?'checked':''}> Automatic (firmware)</label></div>`+field('fan','Manual fan duty',20,100,1,' %','fan'));
  if(['lv3','expert'].includes(level))control+=isCpu?section('ext3','Extended Level 3','Perangkat CPU dapat memerlukan Intel XTU/ThrottleStop dan penguncian BIOS. Tidak ada driver tulis yang dipasang.',`<p class="tune-muted">Monitoring, batas daya rancangan, dan offset undervolt tersimpan dalam profil. CPU fan curve pada kebanyakan laptop dikendalikan EC/firmware, bukan aplikasi web.</p>`):curvePanel();
  if(level==='expert')control+=isCpu?section('expert-panel','Expert / Firmware & Driver','Kapabilitas praktis harus diuji sebelum kontrol fisik diizinkan.',`<div class="tune-expert-grid">${['Speed Shift / EPP · tidak terhubung','Turbo ratios · tidak terhubung','PL1 / PL2 / Tau · tanpa driver','EC fan control · belum diverifikasi','V/F offsets · bergantung mikrocode','Undervolt protection · belum diketahui'].map(x=>`<div>${x}<span>READ ONLY</span></div>`).join('')}</div>`):voltagePanel()+section('expert-panel','Expert / Driver capability','Daftar diagnostik, bukan tombol perubahan hardware.',`<div class="tune-expert-grid">${['Core voltage · belum diverifikasi','GPU clocks · adapter vendor belum tersedia','VRAM timing · belum diperiksa','Fan override · belum diverifikasi','eGPU power budget · belum diperiksa','Driver rollback · not configured'].map(x=>`<div>${x}<span>READ ONLY</span></div>`).join('')}</div>`);
  return `<div class="tune-screen"><div class="tune-banner"><div><span class="tune-kicker">HARDWARE TUNING STUDIO · v2.1.0</span><h2>Performance Profiles</h2><p>Bangun profil OC, UV, power limit, dan kurva respons dengan kontrol interaktif. Proyek aman untuk eksperimen desain profil sebelum dukungan hardware-diverifikasi.</p></div><span class="tune-guard">◈ ${staticWarning}</span></div><div class="tune-stat-grid"><div><span>DEVICE LOAD</span><b id="live-load">${utilization==null?'N/A':Math.round(utilization)+'%'}</b></div><div><span>CORE TEMPERATURE</span><b id="live-temp">${temperature==null?'N/A':Math.round(temperature)+'°C'}</b></div><div><span>DEVICE POWER</span><b id="live-power">${power==null?'N/A':Math.round(power)+' W'}</b></div><div><span>DRIVER WRITE</span><b class="tune-locked">LOCKED</b></div></div><div class="tune-top-controls"><label class="tune-device">TARGET DEVICE <select id="tune-device">${devs.map(d=>`<option value="${fmt(d.id)}" ${d.id===selected?'selected':''}>${fmt(d.name)}</option>`).join('')}</select></label><div class="tune-level-wrap"><span>COMPLEXITY LEVEL</span><div class="tune-levels">${LEVELS.map(([key,title])=>`<button class="tune-level ${level===key?'active':''}" data-level="${key}" aria-pressed="${level===key}">${title}</button>`).join('')}</div></div></div><div class="tune-layout"><div class="tune-main">${control}<div class="tune-actions"><button id="save-tune" class="tune-button primary">Simpan profil lokal</button><button id="undo-tune" class="tune-button">Undo</button><button id="reset-tune" class="tune-button">Reset rancangan</button><button id="export-tune" class="tune-button">Ekspor JSON</button><button id="import-tune" class="tune-button">Impor JSON</button><input type="file" accept="application/json,.json" id="import-tune-file" hidden><button class="tune-button blocked" disabled title="Adapter driver belum diverifikasi. Kontrol hardware secara sengaja dinonaktifkan.">Apply to Hardware · LOCKED</button><span id="tune-message" class="tune-muted" role="status">${dataset[selected]?'Profil tersimpan · pengaturan terakhir dipulihkan':'Belum ada profil tersimpan untuk perangkat ini'}</span></div></div><aside class="tune-aside"><div class="tune-panel tune-guide"><div class="tune-kicker">INFORMATION CENTER</div><h3>Penjelasan kontrol</h3><p id="tune-help-text">Arahkan mouse atau fokus keyboard ke label atau simbol ? untuk memahami fungsi dan risikonya.</p><div class="tune-guide-divider"></div><span class="tune-kicker">CURRENT DEVICE</span><strong>${fmt(isCpu?'CPU · '+(cpu?.name||'Processor'):gpu?.name||'GPU belum terdeteksi')}</strong><p>${snapshot?.demo?'DEMO: sensor di atas adalah simulasi.':'Sensor di atas adalah pembacaan live; N/A berarti tidak tersedia.'} Nilai slider adalah rancangan. Rentang editor bukan batas driver. <span id="tune-capability">${capabilities?'Hardware write terkunci; capability API telah dibaca.':'Memeriksa capability API…'}</span></p><div class="tune-guide-divider"></div><span class="tune-kicker">FAIL-SAFE POLICY</span><p>Tidak ada akses admin, pemanggilan executable OC, modifikasi registri, atau tulis firmware dari halaman ini. Tidak ada Auto Apply pada startup.</p></div></aside></div></div>`;
 }
 function refresh(){const node=document.getElementById('page-content');if(node&&location.hash==='#tuning'){node.innerHTML=output(window.__signaldeckSnapshot);node.dataset.tuningLoaded='yes'}}
 function updateLive(snapshot){window.__signaldeckSnapshot=snapshot;const isCpu=selected==='cpu',d=isCpu?snapshot?.cpu:snapshot?.gpus?.find(g=>gpuKey(g)===selected);
  for(const [id,key,unit] of [['live-load','usage_percent','%'],['live-temp','temperature_c','°C'],['live-power','power_w',' W']]){const node=document.getElementById(id);if(node)node.textContent=d?.[key]==null?'N/A':Math.round(d[key])+unit}
 }
 function setValue(k,v){if(!BOUNDS[k])return;draft[k]=range(v,...BOUNDS[k]);if(k==='cpupl1'||k==='cpupl2'){draft.cpupl2=Math.max(draft.cpupl1,draft.cpupl2);const slider=document.getElementById('tune-cpupl2'),out=document.getElementById('out-cpupl2');if(slider)slider.value=draft.cpupl2;if(out)out.textContent=draft.cpupl2+' W'}const out=document.getElementById('out-'+k);if(out)out.textContent=draft[k]+({'power':' %','core':' MHz','memory':' MHz','target':'°C','fan':' %','cpupl1':' W','cpupl2':' W','cpuuv':' mV'}[k]);}
 function changePoint(key,index,value){
  const fan=key==='fanpoints',min=fan?20:1000,max=fan?100:3000,step=fan?1:10;
  const values=draft[key];values[index]=range(Math.round(value/step)*step,index?values[index-1]:min,index<4?values[index+1]:max);
  const slider=document.querySelector(`[data-${fan?'fan':'vf'}-index="${index}"]`);if(slider)slider.value=values[index];
  const label=document.getElementById((fan?'fan-':'vf-')+index);if(label)label.textContent=values[index]+(fan?'%':' MHz');
  const graphNode=document.getElementById(fan?'tune-curve-chart':'tune-vf-chart');if(graphNode)graphNode.innerHTML=graph(values,fan?[35,45,55,70,85]:[750,800,850,900,950],max,fan?0:min);
 }
 function attach(){document.addEventListener('click',async e=>{
  if(location.hash!=='#tuning')return;
  const lev=e.target.closest('[data-level]');if(lev){level=lev.dataset.level;refresh();return}
  const id=e.target.id;
  if(id==='save-tune'){try{const next={...dataset,[selected]:structuredClone(draft)};localStorage.setItem(STORE,JSON.stringify(next));dataset=next;document.getElementById('tune-message').textContent='Profil tersimpan di browser untuk '+selected}catch(err){document.getElementById('tune-message').textContent='Gagal menyimpan profil: '+err.message}return}
  if(id==='undo-tune'){const prior=undoHistory[selected]?.pop();if(prior){draft=prior;refresh()}return}
  if(id==='reset-tune'){remember();draft=structuredClone(INIT);refresh();return}
  if(id==='export-tune'){const data=JSON.stringify({format:'signaldeck-tuning-draft-v2',device:selected,level,profile:draft,warning:'Profile only; never executed on hardware.'},null,2);const a=document.createElement('a');const url=URL.createObjectURL(new Blob([data],{type:'application/json'}));a.href=url;a.download='signaldeck-tuning-profile.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);return}
  if(id==='import-tune'){document.getElementById('import-tune-file')?.click();return}
  const tip=e.target.closest('[data-tip]');if(tip&&e.detail){document.getElementById('tune-help-text').textContent=DETAILS[tip.dataset.tip]||'Tidak ada informasi tambahan.'}
 });
 document.addEventListener('change',async e=>{if(location.hash!=='#tuning')return;
  if(e.target.id==='tune-device'){working[selected]=structuredClone(draft);selected=e.target.value;load();refresh()}
  if(e.target.id==='tune-auto'){remember();draft.auto=e.target.checked}
  if(e.target.id==='import-tune-file'&&e.target.files?.[0]){try{
   const file=e.target.files[0];if(file.size>20000)throw Error('File melebihi 20 KB');
   const parsed=JSON.parse(await file.text());
   if(parsed.format!=='signaldeck-tuning-draft-v2'||!parsed.profile||Array.isArray(parsed.profile)||typeof parsed.profile!=='object')throw Error('Format profil tidak sesuai');
   const gpu=window.__signaldeckSnapshot?.gpus?.find(g=>gpuKey(g)===selected);
   if(parsed.device!==selected&&parsed.device!==(gpu?'gpu:'+gpu.id:selected))throw Error('Perangkat profil berbeda dari perangkat terpilih');
   const original=parsed.profile;
   for(const [key,[min,max]] of Object.entries(BOUNDS))if(!Number.isFinite(original[key])||original[key]<min||original[key]>max)throw Error('Nilai di luar rentang editor: '+key);
   for(const key of ['fanpoints','corecurve']){
    const values=original[key],min=key==='fanpoints'?20:1000,max=key==='fanpoints'?100:3000;
    if(!Array.isArray(values)||values.length!==5||values.some((v,i)=>!Number.isFinite(v)||v<min||v>max||(i>0&&v<values[i-1])))throw Error('Kurva harus berisi 5 angka dalam rentang dan tidak menurun: '+key);
   }
   if(typeof original.auto!=='boolean'||original.cpupl2<original.cpupl1)throw Error('Mode fan atau PL1/PL2 tidak valid');
   remember();draft=normalized(original);refresh();document.getElementById('tune-message').textContent='Profil diimpor sebagai rancangan (belum disimpan atau diterapkan).';
  }catch(err){document.getElementById('tune-message').textContent='Impor gagal: '+err.message}e.target.value=''}
 });
 document.addEventListener('input',e=>{if(location.hash!=='#tuning')return;
  const k=e.target.dataset.tune;if(k){remember();setValue(k,e.target.value)}
  const i=e.target.dataset.fanIndex;if(i!==undefined){remember();changePoint('fanpoints',+i,+e.target.value)}
  const j=e.target.dataset.vfIndex;if(j!==undefined){remember();changePoint('corecurve',+j,+e.target.value)}
 });
 document.addEventListener('pointerdown',e=>{const point=e.target.closest('[data-curve]');if(!point||location.hash!=='#tuning')return;
  const svg=point.ownerSVGElement,matrix=svg.getScreenCTM();if(!matrix)return;e.preventDefault();remember();
  drag={key:point.dataset.curve,index:+point.dataset.point,inverse:matrix.inverse(),point:svg.createSVGPoint(),id:e.pointerId};
  document.documentElement.setPointerCapture(e.pointerId);
 });
 document.addEventListener('pointermove',e=>{if(!drag||e.pointerId!==drag.id)return;
  drag.point.x=e.clientX;drag.point.y=e.clientY;const y=drag.point.matrixTransform(drag.inverse).y;
  const min=drag.key==='fanpoints'?0:1000,max=drag.key==='fanpoints'?100:3000;
  changePoint(drag.key,drag.index,min+(190-y)/165*(max-min));
 });
 const endDrag=e=>{if(drag&&e.pointerId===drag.id){if(document.documentElement.hasPointerCapture(e.pointerId))document.documentElement.releasePointerCapture(e.pointerId);drag=null}};
 document.addEventListener('pointerup',endDrag);document.addEventListener('pointercancel',endDrag);
 document.addEventListener('keydown',e=>{const point=e.target.closest('[data-curve]');if(!point)return;
  const direction={ArrowUp:1,ArrowRight:1,ArrowDown:-1,ArrowLeft:-1}[e.key];if(!direction)return;
  e.preventDefault();remember();const key=point.dataset.curve,index=+point.dataset.point;
  changePoint(key,index,draft[key][index]+direction*(key==='fanpoints'?1:10)*(e.shiftKey?5:1));
  document.getElementById(`curve-${key}-${index}`)?.focus();
 });
 document.addEventListener('pointerover',e=>{if(location.hash!=='#tuning')return;const el=e.target.closest('[data-help],[data-tip]');if(el){const box=document.getElementById('tune-help-text');if(box)box.textContent=DETAILS[el.dataset.help||el.dataset.tip]||'Lihat dokumentasi perangkat.'}});
 document.addEventListener('focusin',e=>{if(location.hash!=='#tuning')return;const el=e.target.closest('[data-help],[data-tip]');if(el){const box=document.getElementById('tune-help-text');if(box)box.textContent=DETAILS[el.dataset.help||el.dataset.tip]||'Lihat dokumentasi perangkat.'}});
 }
 attach();
 fetch('/api/tuning/capabilities',{cache:'no-store',signal:AbortSignal.timeout(4000)}).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(data=>{capabilities=data;const el=document.getElementById('tune-capability');if(el)el.textContent='Hardware write terkunci; capability API telah dibaca.'}).catch(()=>{const el=document.getElementById('tune-capability');if(el)el.textContent='Capability API tidak tersedia; hardware write tetap terkunci.'});
 return {render(snapshot){window.__signaldeckSnapshot=snapshot;const prior=selected;deviceKey(snapshot);if(loadedDevice!==selected){if(loadedDevice)working[loadedDevice]=structuredClone(draft);load()}return output(snapshot)},updateLive,refresh};
})();
