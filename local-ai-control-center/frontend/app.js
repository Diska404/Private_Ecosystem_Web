const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
const state = {
  page:'dashboard', telemetry:null, status:null, models:[], sessions:[], history:[],
  currentChat:null, currentAgent:null, tpsWindow:60, usageRange:'1m', usage:null,
  tpsSamples:[], gpuHistory:[], resourceHistory:{context:[],gpu0:[],gpu1:[],ram:[]}, ws:null, settings:null, runtimeDirty:false,
  chartConfig:{preset:'telemetry-mix',dashboard:{generation:'wave',context:'gauge',gpu0:'wave',gpu1:'donut',ram:'bar'},usage:{tokens:'wave',models:'bar',clients:'donut',runtime:'timeline',activity:'heatmap'}},
};

const fmt = {
  n(v,d=1){ return (v===null||v===undefined||Number.isNaN(Number(v)))?'—':Number(v).toFixed(d); },
  gb(v){ return `${fmt.n(v,1)} GB`; },
  k(n){ if(n===null||n===undefined) return '—'; n=Number(n); return n>=1024?`${(n/1024).toFixed(n>=10240?0:1)}K`:String(n); },
  duration(sec){ if(sec===null||sec===undefined||!isFinite(sec)) return '—'; sec=Math.max(0,Number(sec)); const h=Math.floor(sec/3600),m=Math.floor((sec%3600)/60),s=Math.floor(sec%60); return h?`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`:`${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`; },
  time(ts){ if(!ts) return '—'; const d=new Date(typeof ts==='number'?ts*1000:ts); return d.toLocaleTimeString('id-ID',{hour:'2-digit',minute:'2-digit',second:'2-digit'}); },
};

async function api(url, opts={}){
  const r = await fetch(url,{headers:{'Content-Type':'application/json',...(opts.headers||{})},...opts});
  const text=await r.text(); let data={}; try{ data=text?JSON.parse(text):{} }catch{data={text}};
  if(!r.ok) throw new Error(data.detail||data.error||text||`HTTP ${r.status}`);
  return data;
}
function toast(msg,type=''){ const el=document.createElement('div'); el.className=`toast ${type}`; el.textContent=msg; $('#toasts').append(el); setTimeout(()=>el.remove(),3800); }
function setRing(el,p,color='var(--blue)'){ if(!el)return; p=Math.max(0,Math.min(100,Number(p)||0)); el.style.setProperty('--p',`${p}%`); el.style.setProperty('--c',color); }
function dotClass(stateName){ if(stateName==='generating')return'generating'; if(stateName==='prompt')return'prompt'; if(stateName==='online')return'online'; if(stateName==='error')return'error'; return stateName==='offline'?'offline':'idle'; }
function currentPageName(){ const m={dashboard:'Dashboard',chat:'Local Chat',agent:'Local Agent',server:'Server',models:'Models',runtime:'Runtime Settings',clients:'Hermes / OpenClaw',hardware:'GPU & Memory',usage:'Usage & Insights',sessions:'Sessions',performance:'Performance',charts:'Chart Studio',logs:'Logs',settings:'Settings'};return m[state.page]||state.page; }

function go(page){
  state.page=page; $$('.page').forEach(x=>x.classList.toggle('active',x.id===`page-${page}`));
  $$('.nav-item').forEach(x=>x.classList.toggle('active',x.dataset.page===page)); $('#pageCrumb').textContent=currentPageName();
  if(page==='models') loadModels(); if(page==='sessions'||page==='performance') loadHistory(); if(page==='usage') loadUsage(state.usageRange); if(page==='charts') { syncChartControls(); renderChartPreview(); } if(page==='logs') loadLogs(); if(page==='settings') loadSettings(); if(page==='runtime') fillRuntimeForm(); if(page==='server') refreshServer();
  history.replaceState(null,'',`#${page}`);
}
$$('[data-page]').forEach(b=>b.onclick=()=>go(b.dataset.page)); $$('[data-go]').forEach(b=>b.onclick=()=>go(b.dataset.go));
$('#toggleSidebar').onclick=()=>$('#sidebar').classList.toggle('collapsed');
setInterval(()=>$('#clock').textContent=new Date().toLocaleTimeString('id-ID'),500);

function activeContext(){
  let session=null;
  if(state.page==='chat'&&state.currentChat) session=state.sessions.find(s=>s.id===state.currentChat);
  if(state.page==='agent'&&state.currentAgent) session=state.sessions.find(s=>s.id===state.currentAgent);
  if(session) return session.context||{used:session.context_used||0,capacity:session.context_capacity||65536};
  const clients=state.telemetry?.clients||{};
  const active=Object.entries(clients).find(([,v])=>v.active&&v.context)?.[1]?.context;
  if(active) return {used:active.used||0,capacity:active.capacity||65536,source:active.source};
  const rt=state.status?.config?.runtime||state.telemetry?.runtime?.runtime||{};
  return {used:0,capacity:rt.context_size||65536,source:'runtime'};
}
function updateContextUI(){
  const c=activeContext(), used=Number(c.used||0), cap=Number(c.capacity||65536), pct=cap?used/cap*100:0, remain=Math.max(0,cap-used);
  $('#topContextValue').textContent=`${fmt.k(used)} / ${fmt.k(cap)}`; $('#topContextBar').style.width=`${Math.min(100,pct)}%`;
  $('#contextPct').textContent=`${pct.toFixed(0)}%`; $('#contextMain').textContent=`${fmt.k(used)} / ${fmt.k(cap)}`; $('#contextSub').textContent=`${fmt.k(remain)} remaining`; setRing($('#contextRing'),pct,pct>90?'var(--red)':pct>75?'var(--amber)':'var(--blue)');
  $('#chatContextValue').textContent=`${fmt.k(used)} / ${fmt.k(cap)}`; $('#chatContextBar').style.width=`${Math.min(100,pct)}%`; $('#chatContextRemain').textContent=`${fmt.k(remain)} remaining`;
}

function updateTelemetry(t){
  state.telemetry=t;
  const llama=t.llama||{}, procs=t.processes||{}, runtime=t.runtime||{};
  const managed=runtime.managed, external=runtime.external||[]; const serverOnline=!!managed||external.length>0||!!procs.llama?.length;
  const stateName=serverOnline?(llama.state||'idle'):'offline';
  $('#sideDot').className=`dot ${dotClass(serverOnline?'online':'offline')}`; $('#sideStatus').textContent=serverOnline?'Runtime online':'Runtime offline';
  $('#runtimeStripDot').className=`dot ${dotClass(serverOnline?'online':'offline')}`; $('#runtimeStrip').textContent=serverOnline?'llama-server terhubung':'Runtime belum terhubung';
  const rt=runtime.runtime||{}; const mp=rt.model_path||''; $('#runtimeModel').textContent=`Model: ${mp?mp.replaceAll('\\','/').split('/').pop():'—'}`; $('#runtimeContext').textContent=`Context: ${fmt.k(rt.context_size||65536)}`;
  $('#kpiState').textContent=stateName.toUpperCase(); $('#kpiStateSub').textContent=stateName==='generating'?'Model sedang menghasilkan token':stateName==='prompt'?'Memproses prompt/context':serverOnline?'Menunggu request':'Server offline';
  $('#kpiGen').textContent=llama.generation_tps!=null?fmt.n(llama.generation_tps,2):'—'; $('#kpiPrompt').textContent=llama.prompt_tps!=null?fmt.n(llama.prompt_tps,2):'—';
  $('#railGen').textContent=llama.generation_tps!=null?fmt.n(llama.generation_tps,2):'—'; $('#railPrompt').textContent=llama.prompt_tps!=null?fmt.n(llama.prompt_tps,2):'—'; $('#railState').textContent=stateName.toUpperCase();
  const up=managed?.uptime_seconds || (procs.llama?.[0]?.create_time?Date.now()/1000-procs.llama[0].create_time:null); $('#kpiUptime').textContent=fmt.duration(up);
  $('#globalClient').innerHTML=`<span class="dot ${dotClass(stateName)}"></span><span>${stateName==='offline'?'Disconnected':stateName.toUpperCase()}</span>`;

  const now=Date.now()/1000;
  if(llama.generation_tps!=null && (state.tpsSamples.length===0 || now-state.tpsSamples[state.tpsSamples.length-1].ts>.35)) state.tpsSamples.push({ts:now,v:Number(llama.generation_tps)});
  state.tpsSamples=state.tpsSamples.filter(x=>now-x.ts<900);
  const gpus=t.gpus||[]; state.gpuHistory.push({ts:now,vals:gpus.map(g=>g.utilization)}); state.gpuHistory=state.gpuHistory.filter(x=>now-x.ts<900);
  updateResources(gpus,t.system||{}); updateClients(t.clients||{}); updateContextUI(); drawTps(); drawGpu();
}

function updateResources(gpus,sys){
  for(let i=0;i<2;i++){
    const g=gpus[i], ring=$(`#gpu${i}Ring`), pct=$(`#gpu${i}Pct`), main=$(`#gpu${i}Main`), sub=$(`#gpu${i}Sub`), card=$(`#gpu${i}Card`);
    if(!g){ pct.textContent='—';main.textContent='GPU not found';sub.textContent='—';setRing(ring,0);continue; }
    const mp=Number(g.memory_percent||0); pct.textContent=`${mp.toFixed(0)}%`; main.textContent=`${fmt.n(g.memory_used_gb,1)} / ${fmt.n(g.memory_total_gb,1)} GB`; sub.textContent=`${g.name} · ${fmt.n(g.utilization,0)}% GPU · ${fmt.n(g.temperature_c,0)}°C · ${fmt.n(g.power_w,0)}W`; setRing(ring,mp,mp>92?'var(--red)':mp>82?'var(--amber)':'var(--blue)'); card.querySelector('.resource-title').textContent=`GPU ${g.index} · ${g.name}`;
  }
  const rp=Number(sys.ram_percent||0); $('#ramPct').textContent=`${rp.toFixed(0)}%`; $('#ramMain').textContent=`${fmt.n(sys.ram_used_gb,1)} / ${fmt.n(sys.ram_total_gb,1)} GB`; $('#ramSub').textContent=`CPU ${fmt.n(sys.cpu_percent,0)}%`; setRing($('#ramRing'),rp,rp>90?'var(--red)':rp>80?'var(--amber)':'var(--blue)');
  $('#railHardware').innerHTML=(gpus.slice(0,2).map(g=>`<div class="hw-line"><span><b>${g.name}</b><em>${fmt.n(g.utilization,0)}% · ${fmt.n(g.memory_used_gb,1)}G</em></span><div class="mini-bar"><i style="width:${Math.min(100,g.memory_percent)}%"></i></div></div>`).join(''))+`<div class="hw-line"><span><b>RAM</b><em>${fmt.n(sys.ram_percent,0)}%</em></span><div class="mini-bar"><i style="width:${Math.min(100,sys.ram_percent||0)}%"></i></div></div>`;
  renderHardwareCards(gpus,sys);
}

function updateClients(clients){
  const labels={'hermes':'Hermes','openclaw':'OpenClaw','web-chat':'Web Chat','web-agent':'Web Agent'};
  const rows=Object.entries(labels).map(([k,label])=>{ const c=clients[k]||{}; const status=c.active?'GENERATING':c.connected?'CONNECTED':'OFFLINE'; return `<div class="client-row"><span class="dot ${c.active?'generating':c.connected?'online':'offline'}"></span><div class="grow"><b>${label}</b><small>${status}${c.context?` · ${fmt.k(c.context.used)}/${fmt.k(c.context.capacity)}`:''}</small></div></div>`; }).join('');
  $('#dashClients').innerHTML=rows;
  $('#clientCards').innerHTML=Object.entries(labels).map(([k,label])=>{const c=clients[k]||{},ctx=c.context||{};return `<div class="client-card"><div class="head"><span class="dot ${c.active?'generating':c.connected?'online':'offline'}"></span><h3>${label}</h3></div><div class="stats"><div><span>STATUS</span><b>${c.active?'ACTIVE':c.connected?'CONNECTED':'OFFLINE'}</b></div><div><span>CONTEXT</span><b>${ctx.capacity?`${fmt.k(ctx.used)}/${fmt.k(ctx.capacity)}`:'—'}</b></div><div><span>PROCESS</span><b>${c.processes?.[0]?.pid||'—'}</b></div></div></div>`}).join('');
}

function canvasSize(c){ const dpr=window.devicePixelRatio||1,rect=c.getBoundingClientRect(); const w=Math.max(10,rect.width),h=Math.max(10,rect.height); if(c.width!==Math.floor(w*dpr)||c.height!==Math.floor(h*dpr)){c.width=Math.floor(w*dpr);c.height=Math.floor(h*dpr);} const ctx=c.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0); return {ctx,w,h}; }
function drawLineChart(canvas,samples,series=1,colors=['#316fe9','#75a0ef']){
  if(!canvas)return; const {ctx,w,h}=canvasSize(canvas);ctx.clearRect(0,0,w,h); const pad={l:38,r:12,t:12,b:25},iw=w-pad.l-pad.r,ih=h-pad.t-pad.b; ctx.strokeStyle='#e9edf3';ctx.lineWidth=1;ctx.font='10px Segoe UI';ctx.fillStyle='#91a0b2';
  let all=[]; samples.forEach(s=>{if(series===1)all.push(s.v||0);else all.push(...(s.vals||[]).filter(v=>v!=null));}); let max=Math.max(10,...all)*1.15; max=Math.ceil(max/5)*5;
  for(let i=0;i<=4;i++){const y=pad.t+ih*i/4;ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(w-pad.r,y);ctx.stroke();ctx.fillText(String(Math.round(max*(1-i/4))),5,y+3)}
  if(samples.length<2)return; const t0=samples[0].ts,t1=samples[samples.length-1].ts||t0+1;
  for(let si=0;si<series;si++){ctx.strokeStyle=colors[si%colors.length];ctx.lineWidth=2;ctx.beginPath();let started=false;samples.forEach(s=>{const v=series===1?s.v:(s.vals||[])[si];if(v==null)return;const x=pad.l+(s.ts-t0)/(Math.max(.001,t1-t0))*iw,y=pad.t+ih-(v/max)*ih;if(!started){ctx.moveTo(x,y);started=true}else ctx.lineTo(x,y)});ctx.stroke();}
}
function drawTps(){ const now=Date.now()/1000,win=state.tpsWindow; const samples=state.tpsSamples.filter(x=>now-x.ts<=win); $('#tpsEmpty').style.display=samples.length>1?'none':'grid'; drawLineChart($('#tpsChart'),samples,1); }
function drawGpu(){ const now=Date.now()/1000;drawLineChart($('#gpuChart'),state.gpuHistory.filter(x=>now-x.ts<=300),2,['#316fe9','#69a97a']); }
$$('[data-window]').forEach(b=>b.onclick=()=>{$$('[data-window]').forEach(x=>x.classList.remove('active'));b.classList.add('active');state.tpsWindow=Number(b.dataset.window);drawTps()});
window.addEventListener('resize',()=>{drawTps();drawGpu();if(state.usage)renderUsageCharts();renderChartPreview()});

async function refreshStatus(){ try{state.status=await api('/api/status'); if(state.status?.config?.charts) state.chartConfig=JSON.parse(JSON.stringify(state.status.config.charts)); fillRuntimeForm(false);updateContextUI();syncChartControls();}catch(e){console.warn(e)} }
async function refreshServer(){ try{const d=await api('/api/runtime');const s=d.status, h=d.health; $('#serverStatus').innerHTML=`<dt>Health</dt><dd>${h.ok?'CONNECTED':'DISCONNECTED'} · ${h.url||''}</dd><dt>Managed PID</dt><dd>${s.managed?.pid||'—'}</dd><dt>External server</dt><dd>${s.external?.length?s.external.map(x=>x.pid).join(', '):'—'}</dd><dt>Model</dt><dd>${s.runtime?.model_path||'—'}</dd><dt>Context</dt><dd>${fmt.k(s.runtime?.context_size||0)}</dd><dt>Executable</dt><dd>${s.llama_server_path||'Not found in PATH'}</dd>`; await refreshServerLog();}catch(e){toast(e.message,'error')} }
async function refreshServerLog(){const d=await api('/api/logs/llama?tail=120');$('#serverLog').textContent=d.text||'No log.'}
$('#startServerBtn').onclick=async()=>{try{toast('Starting llama-server...');await api('/api/runtime/start',{method:'POST',body:'{}'});toast('Runtime started','success');refreshServer()}catch(e){toast(e.message,'error')}};
$('#stopServerBtn').onclick=async()=>{try{await api('/api/runtime/stop',{method:'POST',body:'{}'});toast('Runtime stopped','success');refreshServer()}catch(e){toast(e.message,'error')}};

async function loadModels(){ try{const d=await api('/api/models');state.models=d.models||[];renderModels();}catch(e){toast(e.message,'error')} }
function renderModels(){const active=state.status?.config?.runtime?.model_path||state.telemetry?.runtime?.runtime?.model_path||'';$('#modelList').innerHTML=state.models.length?state.models.map(m=>`<div class="model-card ${active===m.path?'loaded':''}"><div><h3>${escapeHtml(m.name)}</h3><p>${escapeHtml(m.path)}</p><div class="model-tags"><span class="tag blue">${m.quant||'GGUF'}</span><span class="tag">${m.role}</span>${m.role==='mtp-sidecar'?'<span class="tag amber">Sidecar, bukan main model</span>':''}</div></div><div class="model-actions"><strong>${m.size_gb.toFixed(2)} GB</strong>${m.role==='model'?`<button class="${active===m.path?'secondary':'primary'}" onclick="selectModel(${JSON.stringify(m.path).replaceAll('"','&quot;')})">${active===m.path?'Loaded':'Use Model'}</button>`:''}</div></div>`).join(''):'<div class="empty-state">Tidak ada GGUF ditemukan. Atur scan path di Settings.</div>';}
window.selectModel=async(path)=>{try{await api('/api/runtime/config',{method:'POST',body:JSON.stringify({model_path:path})});state.status=await api('/api/status');fillRuntimeForm();renderModels();toast('Model dipilih. Restart server untuk load.','success');}catch(e){toast(e.message,'error')}};
$('#rescanModelsBtn').onclick=loadModels;

function fillRuntimeForm(force=true){ const rt=state.status?.config?.runtime||state.telemetry?.runtime?.runtime;if(!rt)return;if(!force&&document.activeElement?.closest?.('#page-runtime'))return; $('#rtModelPath').value=rt.model_path||'';$('#rtServerPath').value=rt.llama_server_path||'';$('#rtGpuLayers').value=rt.gpu_layers??'auto';$('#rtMainGpu').value=rt.main_gpu??0;$('#rtTensorSplit').value=rt.tensor_split||'';$('#rtParallel').value=rt.parallel||1;$('#rtCacheK').value=rt.cache_type_k||'q8_0';$('#rtCacheV').value=rt.cache_type_v||'q8_0';$('#rtBatch').value=rt.batch_size||2048;$('#rtUBatch').value=rt.ubatch_size||512;$('#rtFitTarget').value=rt.fit_target_mib||1536;$('#rtExtra').value=rt.extra_args||'';$('#rtFlash').checked=!!rt.flash_attention;$('#rtMtp').checked=!!rt.mtp;$('#rtFit').checked=!!rt.fit; renderContextPresets(rt.context_size||65536); }
function renderContextPresets(active){ const vals=[1024,2048,4096,8192,16384,32768,65536,131072];$('#contextPresets').innerHTML=vals.map(v=>`<button class="${Number(active)===v?'active':''}" data-ctx="${v}">${fmt.k(v)}</button>`).join('');$$('#contextPresets button').forEach(b=>b.onclick=()=>{$$('#contextPresets button').forEach(x=>x.classList.remove('active'));b.classList.add('active');state.runtimeDirty=true})}
function runtimeForm(){return{model_path:$('#rtModelPath').value.trim(),llama_server_path:$('#rtServerPath').value.trim(),context_size:Number($('#contextPresets .active')?.dataset.ctx||65536),gpu_layers:$('#rtGpuLayers').value.trim()||'auto',main_gpu:Number($('#rtMainGpu').value||0),tensor_split:$('#rtTensorSplit').value.trim(),parallel:Number($('#rtParallel').value||1),cache_type_k:$('#rtCacheK').value,cache_type_v:$('#rtCacheV').value,batch_size:Number($('#rtBatch').value||2048),ubatch_size:Number($('#rtUBatch').value||512),fit_target_mib:Number($('#rtFitTarget').value||1536),extra_args:$('#rtExtra').value.trim(),flash_attention:$('#rtFlash').checked,mtp:$('#rtMtp').checked,fit:$('#rtFit').checked}}
$('#applyRestartBtn').onclick=async()=>{try{const p=runtimeForm();toast('Applying runtime settings...');await api('/api/runtime/config',{method:'POST',body:JSON.stringify(p)});await api('/api/runtime/restart',{method:'POST',body:JSON.stringify(p)});state.status=await api('/api/status');toast('Runtime restarted dengan konfigurasi baru.','success')}catch(e){toast(e.message,'error')}};

async function loadSessions(){try{const d=await api('/api/sessions');state.sessions=d.sessions||[];renderSessionLists();updateContextUI()}catch(e){console.warn(e)}}
function renderSessionLists(){ const chat=state.sessions.filter(s=>s.mode==='chat'&&s.client==='web-chat'); $('#chatSessions').innerHTML=chat.map(s=>`<div class="session-item ${state.currentChat===s.id?'active':''}" data-chat-id="${s.id}"><b>${escapeHtml(s.title)}</b><small>${escapeHtml(s.model_name||'Local model')} · ${fmt.k(s.context_used||0)}/${fmt.k(s.context_capacity||65536)}</small></div>`).join('');$$('[data-chat-id]').forEach(x=>x.onclick=()=>openChat(x.dataset.chatId)); }
async function newSession(mode='chat'){ const rt=state.status?.config?.runtime||{}; const client=mode==='agent'?'web-agent':'web-chat'; const s=await api('/api/sessions',{method:'POST',body:JSON.stringify({title:mode==='agent'?'New Agent':'New Chat',client,mode,context_capacity:rt.context_size||65536,model_path:rt.model_path||'',model_name:(rt.model_path||'').replaceAll('\\','/').split('/').pop()||'local-model'})}); await loadSessions(); if(mode==='agent'){state.currentAgent=s.id;$('#agentSessionLabel').textContent=s.title;$('#agentMessages').innerHTML='';}else openChat(s.id); return s; }
$('#newChatBtn').onclick=()=>newSession('chat').catch(e=>toast(e.message,'error')); $('#newAgentBtn').onclick=()=>newSession('agent').catch(e=>toast(e.message,'error'));
async function openChat(id){state.currentChat=id;renderSessionLists();const s=await api(`/api/sessions/${id}`);$('#chatTitle').textContent=s.title;$('#chatMeta').textContent=`${s.model_name||'Local model'} · Context ${fmt.k(s.context_capacity)}`; const box=$('#chatMessages');box.innerHTML='';(s.messages||[]).forEach(m=>appendMessage(box,m.role,m.content)); updateContextUI();box.scrollTop=box.scrollHeight;}
function appendMessage(box,role,content=''){const wrap=document.createElement('div');wrap.className=`message ${role==='user'?'user':'assistant'}`;wrap.innerHTML=`<div class="message-label">${role==='user'?'YOU':'LOCAL AI'}</div><div class="bubble"></div>`;wrap.querySelector('.bubble').textContent=content;box.append(wrap);return wrap.querySelector('.bubble')}
function escapeHtml(s){return String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}

async function consumeSSE(resp,onData){ const reader=resp.body.getReader(),dec=new TextDecoder();let buf='';while(true){const {value,done}=await reader.read();if(done)break;buf+=dec.decode(value,{stream:true});const parts=buf.split('\n\n');buf=parts.pop()||'';for(const part of parts){const line=part.split('\n').find(x=>x.startsWith('data:'));if(!line)continue;const raw=line.slice(5).trim();if(raw==='[DONE]')continue;try{onData(JSON.parse(raw))}catch{}}}}
$('#sendChatBtn').onclick=sendChat; $('#chatInput').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendChat()}});
async function sendChat(){try{if(!state.currentChat)await newSession('chat');const inp=$('#chatInput'),msg=inp.value.trim();if(!msg)return;inp.value='';const box=$('#chatMessages');if(box.querySelector('.welcome-card'))box.innerHTML='';appendMessage(box,'user',msg);const bubble=appendMessage(box,'assistant','');box.scrollTop=box.scrollHeight;const resp=await fetch(`/api/chat/${state.currentChat}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg,temperature:Number($('#temperature').value),top_p:Number($('#topP').value),max_tokens:Number($('#maxTokens').value)})});if(!resp.ok)throw new Error(await resp.text());await consumeSSE(resp,obj=>{const choices=obj.choices||[];const d=choices[0]?.delta?.content;if(d){bubble.textContent+=d;box.scrollTop=box.scrollHeight}});await loadSessions();await openChat(state.currentChat);}catch(e){toast(e.message,'error')}}

$('#sendAgentBtn').onclick=sendAgent; $('#agentInput').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendAgent()}});
async function sendAgent(){try{if(!state.currentAgent)await newSession('agent');const inp=$('#agentInput'),msg=inp.value.trim();if(!msg)return;inp.value='';const box=$('#agentMessages');appendMessage(box,'user',msg);const bubble=appendMessage(box,'assistant','');$('#agentActivity').innerHTML='';$('#agentState').textContent='RUNNING';const resp=await fetch(`/api/agent/${state.currentAgent}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg,permission_profile:$('#agentPermission').value})});if(!resp.ok)throw new Error(await resp.text());await consumeSSE(resp,obj=>{if(obj.type==='assistant'&&obj.content){bubble.textContent+=obj.content;box.scrollTop=box.scrollHeight}if(obj.type==='status')addActivity(`State: ${obj.state}`,obj,'');if(obj.type==='tool_call')addActivity(`Tool: ${obj.name}`,obj.arguments,'');if(obj.type==='tool_result')addActivity(`Result: ${obj.name}`,obj.result,obj.result?.ok?'success':'error');if(obj.type==='error')addActivity('Agent Error',{message:obj.message},'error');if(obj.type==='done')$('#agentState').textContent='IDLE'});await loadSessions();}catch(e){$('#agentState').textContent='ERROR';toast(e.message,'error')}}
function addActivity(title,data,cls=''){const d=document.createElement('div');d.className=`activity-item ${cls}`;d.innerHTML=`<b>${escapeHtml(title)}</b><pre>${escapeHtml(JSON.stringify(data,null,2))}</pre>`;$('#agentActivity').prepend(d)}

function renderHardwareCards(gpus,sys){ const cards=gpus.map(g=>`<div class="hardware-card"><h3>${escapeHtml(g.name)}</h3><div class="metric-line"><span>GPU Load</span><b>${fmt.n(g.utilization,0)}%</b></div><div class="mini-bar"><i style="width:${Math.min(100,g.utilization)}%"></i></div><div class="metric-line"><span>VRAM</span><b>${fmt.n(g.memory_used_gb,1)} / ${fmt.n(g.memory_total_gb,1)} GB</b></div><div class="mini-bar"><i style="width:${Math.min(100,g.memory_percent)}%"></i></div><div class="metric-line"><span>Temperature</span><b>${fmt.n(g.temperature_c,0)}°C</b></div><div class="metric-line"><span>Power</span><b>${fmt.n(g.power_w,1)} W</b></div><div class="metric-line"><span>Clock</span><b>${fmt.n(g.clock_mhz,0)} MHz</b></div></div>`);cards.push(`<div class="hardware-card"><h3>System</h3><div class="metric-line"><span>CPU</span><b>${fmt.n(sys.cpu_percent,0)}%</b></div><div class="mini-bar"><i style="width:${Math.min(100,sys.cpu_percent||0)}%"></i></div><div class="metric-line"><span>RAM</span><b>${fmt.n(sys.ram_used_gb,1)} / ${fmt.n(sys.ram_total_gb,1)} GB</b></div><div class="mini-bar"><i style="width:${Math.min(100,sys.ram_percent||0)}%"></i></div><div class="metric-line"><span>Logical CPU</span><b>${sys.cpu_count||'—'}</b></div></div>`);$('#hardwareCards').innerHTML=cards.join('')}

async function loadHistory(){try{const d=await api('/api/history?limit=300');state.history=d.runs||[];renderHistory();renderPerformance();renderLastInference()}catch(e){toast(e.message,'error')}}
function renderHistory(){const body=$('#historyBody');body.innerHTML=state.history.map(r=>`<tr><td>${fmt.time(r.started_at)}</td><td>${escapeHtml(r.client)}</td><td title="${escapeHtml(r.model_name||'')}">${escapeHtml((r.model_name||'—').slice(0,38))}</td><td>${fmt.k(r.context_used||0)}/${fmt.k(r.context_capacity||0)}</td><td>${r.prompt_tokens??'—'}</td><td>${r.output_tokens??'—'}</td><td>${r.generation_tps!=null?fmt.n(r.generation_tps,2):'—'}</td><td>${fmt.duration(r.total_duration)}</td></tr>`).join('')||'<tr><td colspan="8">Belum ada history.</td></tr>'}
function renderLastInference(){const r=state.history[0];if(!r){$('#lastInference').className='last-inference empty-state';$('#lastInference').textContent='Belum ada inference yang tercatat.';return}$('#lastInference').className='last-inference';$('#lastInference').innerHTML=`<div class="metric"><span>CLIENT</span><b>${escapeHtml(r.client)}</b></div><div class="metric"><span>GEN TPS</span><b>${r.generation_tps!=null?fmt.n(r.generation_tps,2):'—'}</b></div><div class="metric"><span>DURATION</span><b>${fmt.duration(r.total_duration)}</b></div><div class="metric"><span>PROMPT</span><b>${r.prompt_tokens??'—'}</b></div><div class="metric"><span>OUTPUT</span><b>${r.output_tokens??'—'}</b></div><div class="metric"><span>CONTEXT</span><b>${fmt.k(r.context_used||0)}/${fmt.k(r.context_capacity||0)}</b></div>`}
function renderPerformance(){const groups={};state.history.filter(r=>r.generation_tps>0).forEach(r=>{const k=`${r.model_name||'Unknown'}|${r.quantization||'GGUF'}`;groups[k]??={name:(r.model_name||'Unknown').slice(0,45),quant:r.quantization||'GGUF',n:0,sum:0,prompt:0,pn:0};groups[k].n++;groups[k].sum+=r.generation_tps;if(r.prompt_tps){groups[k].prompt+=r.prompt_tps;groups[k].pn++}});const arr=Object.values(groups).map(g=>({...g,avg:g.sum/g.n,pavg:g.pn?g.prompt/g.pn:0})).sort((a,b)=>b.avg-a.avg);const best=arr[0];$('#compareGrid').innerHTML=[['Models tested',arr.length],['Best avg TPS',best?fmt.n(best.avg,2):'—'],['Inference runs',state.history.length],['Top model',best?best.quant:'—']].map(([a,b])=>`<div class="compare-card"><span>${a}</span><b>${escapeHtml(b)}</b><small>Local benchmark history</small></div>`).join('');const max=Math.max(1,...arr.map(x=>x.avg));$('#modelBars').innerHTML=arr.slice(0,10).map(g=>`<div class="bar-row"><span>${escapeHtml(g.quant)} · ${escapeHtml(g.name.slice(0,24))}</span><div class="bar-track"><i style="width:${g.avg/max*100}%"></i></div><b>${fmt.n(g.avg,2)}</b></div>`).join('')||'<div class="empty-state">Belum cukup data.</div>'}
$('#refreshHistoryBtn').onclick=loadHistory;

async function loadLogs(){try{const [l,e]=await Promise.all([api('/api/logs/llama?tail=500'),api('/api/events?limit=200')]);$('#llamaLog').textContent=l.text||'No log.';$('#eventList').innerHTML=(e.events||[]).map(x=>`<div class="event-row"><b>${escapeHtml(x.source)} · ${escapeHtml(x.level)}</b><span>${escapeHtml(x.message)}</span><small>${escapeHtml(x.created_at)}</small></div>`).join('')||'<div class="empty-state">No events.</div>'}catch(e){toast(e.message,'error')}}
$('#refreshLogsBtn').onclick=loadLogs;

async function loadSettings(){try{state.settings=await api('/api/config');if(state.settings.charts)state.chartConfig=clone(state.settings.charts);$('#settingScanPaths').value=(state.settings.models.scan_paths||[]).join('\n');$('#settingHermesLog').value=state.settings.clients.hermes_log||'';$('#settingTelemetry').value=state.settings.app.telemetry_interval_ms||500;$('#settingAgentPermission').value=state.settings.agent.permission_profile||'safe';syncChartControls();applyChartsNow()}catch(e){toast(e.message,'error')}}
$('#saveSettingsBtn').onclick=async()=>{try{const p={models:{scan_paths:$('#settingScanPaths').value.split('\n').map(x=>x.trim()).filter(Boolean)},clients:{hermes_log:$('#settingHermesLog').value.trim()},app:{telemetry_interval_ms:Number($('#settingTelemetry').value||500)},agent:{permission_profile:$('#settingAgentPermission').value}};await api('/api/config',{method:'POST',body:JSON.stringify(p)});toast('Settings saved','success');await loadModels()}catch(e){toast(e.message,'error')}};

$$('[data-copy-target]').forEach(b=>b.onclick=async()=>{const t=$(`#${b.dataset.copyTarget}`).textContent;await navigator.clipboard.writeText(t);toast('Copied','success')});



// ---------------- Usage analytics + visualization studio (v0.2) ----------------
fmt.big=function(n){n=Number(n||0);const a=Math.abs(n);if(a>=1e9)return`${(n/1e9).toFixed(a>=1e10?1:2)}B`;if(a>=1e6)return`${(n/1e6).toFixed(a>=1e7?1:2)}M`;if(a>=1e3)return`${(n/1e3).toFixed(a>=1e4?1:2)}K`;return String(Math.round(n))};
fmt.hours=function(sec){sec=Number(sec||0);if(sec<3600)return fmt.duration(sec);const h=sec/3600;return h>=100?`${h.toFixed(0)} h`:`${h.toFixed(1)} h`};

const CHART_PRESETS={
  'telemetry-mix':{dashboard:{generation:'wave',context:'gauge',gpu0:'wave',gpu1:'donut',ram:'bar'},usage:{tokens:'wave',models:'bar',clients:'donut',runtime:'timeline',activity:'heatmap'}},
  'wave-focus':{dashboard:{generation:'wave',context:'wave',gpu0:'wave',gpu1:'wave',ram:'wave'},usage:{tokens:'wave',models:'line',clients:'bar',runtime:'timeline',activity:'heatmap'}},
  'performance-lines':{dashboard:{generation:'line',context:'line',gpu0:'line',gpu1:'line',ram:'line'},usage:{tokens:'line',models:'bar',clients:'bar',runtime:'timeline',activity:'heatmap'}},
  'capacity':{dashboard:{generation:'step',context:'gauge',gpu0:'gauge',gpu1:'donut',ram:'bar'},usage:{tokens:'bar',models:'donut',clients:'donut',runtime:'timeline',activity:'heatmap'}},
  'minimal':{dashboard:{generation:'line',context:'bar',gpu0:'bar',gpu1:'bar',ram:'bar'},usage:{tokens:'line',models:'bar',clients:'bar',runtime:'timeline',activity:'heatmap'}}
};

function clone(o){return JSON.parse(JSON.stringify(o))}
function chartType(path,fallback){const parts=path.split('.');let v=state.chartConfig;for(const p of parts)v=v?.[p];return v||fallback}
function palette(i){return ['#316fe9','#65a3f3','#5eb68a','#d4a23e','#7e73d8','#d96779','#5f7f9f','#99a6b5'][i%8]}
function prepCanvas(c){if(!c)return null;const {ctx,w,h}=canvasSize(c);ctx.clearRect(0,0,w,h);ctx.lineCap='round';ctx.lineJoin='round';return{ctx,w,h}}
function drawEmptyCanvas(c,text='Belum ada data'){const z=prepCanvas(c);if(!z)return;z.ctx.fillStyle='#97a3b1';z.ctx.font='10px Segoe UI';z.ctx.textAlign='center';z.ctx.fillText(text,z.w/2,z.h/2)}

function drawTrend(canvas,values,type='line',opts={}){
  const z=prepCanvas(canvas);if(!z)return;const {ctx,w,h}=z;const vals=(values||[]).map(Number).filter(Number.isFinite);if(!vals.length){drawEmptyCanvas(canvas);return}
  const pad=opts.compact?{l:5,r:5,t:7,b:7}:{l:34,r:10,t:12,b:22},iw=w-pad.l-pad.r,ih=h-pad.t-pad.b;
  const max=Math.max(opts.maxY||0,...vals,1)*1.08,min=opts.minY??0,span=Math.max(.0001,max-min);
  if(!opts.compact){ctx.strokeStyle='#e9edf3';ctx.lineWidth=1;ctx.font='9px Segoe UI';ctx.fillStyle='#91a0b2';ctx.textAlign='left';for(let i=0;i<=3;i++){const y=pad.t+ih*i/3;ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(w-pad.r,y);ctx.stroke();ctx.fillText(fmt.big(max*(1-i/3)),3,y+3)}}
  const pts=vals.map((v,i)=>({x:pad.l+(vals.length===1?iw/2:i/(vals.length-1)*iw),y:pad.t+ih-(v-min)/span*ih,v}));
  if(type==='bar'){
    const bw=Math.max(2,Math.min(24,iw/vals.length*.64));ctx.fillStyle=opts.color||'#4f86e7';pts.forEach(p=>ctx.fillRect(p.x-bw/2,p.y,bw,pad.t+ih-p.y));return;
  }
  if(type==='wave'){
    const g=ctx.createLinearGradient(0,pad.t,0,pad.t+ih);g.addColorStop(0,'rgba(49,111,233,.30)');g.addColorStop(1,'rgba(49,111,233,.025)');ctx.beginPath();ctx.moveTo(pts[0].x,pad.t+ih);pts.forEach((p,i)=>{if(i===0)ctx.lineTo(p.x,p.y);else{const prev=pts[i-1],cx=(prev.x+p.x)/2;ctx.bezierCurveTo(cx,prev.y,cx,p.y,p.x,p.y)}});ctx.lineTo(pts.at(-1).x,pad.t+ih);ctx.closePath();ctx.fillStyle=g;ctx.fill();
  }
  ctx.strokeStyle=opts.color||'#316fe9';ctx.lineWidth=2;ctx.beginPath();
  pts.forEach((p,i)=>{if(i===0)ctx.moveTo(p.x,p.y);else if(type==='step'){ctx.lineTo(p.x,pts[i-1].y);ctx.lineTo(p.x,p.y)}else{ctx.lineTo(p.x,p.y)}});ctx.stroke();
  if(type==='dots'){ctx.fillStyle=opts.color||'#316fe9';pts.forEach(p=>{ctx.beginPath();ctx.arc(p.x,p.y,3,0,Math.PI*2);ctx.fill()})}
}

function drawDonut(canvas,items,centerText=''){
  const z=prepCanvas(canvas);if(!z)return;const {ctx,w,h}=z;const clean=(items||[]).filter(x=>Number(x.value)>0),total=clean.reduce((a,b)=>a+Number(b.value),0);if(!total){drawEmptyCanvas(canvas);return}
  const cx=w/2,cy=h/2,r=Math.min(w,h)*.34,lw=Math.max(10,r*.34);let a=-Math.PI/2;
  clean.forEach((it,i)=>{const da=Number(it.value)/total*Math.PI*2;ctx.beginPath();ctx.strokeStyle=palette(i);ctx.lineWidth=lw;ctx.arc(cx,cy,r,a,a+da);ctx.stroke();a+=da});
  ctx.textAlign='center';ctx.fillStyle='#2d435e';ctx.font='700 14px Segoe UI';ctx.fillText(centerText||fmt.big(total),cx,cy+3);ctx.font='8px Segoe UI';ctx.fillStyle='#8997a8';ctx.fillText('TOTAL',cx,cy+17);
}
function drawGauge(canvas,pct){const z=prepCanvas(canvas);if(!z)return;const{ctx,w,h}=z;const p=Math.max(0,Math.min(100,Number(pct)||0)),cx=w/2,cy=h*.74,r=Math.min(w*.35,h*.58);ctx.lineWidth=Math.max(10,r*.23);ctx.strokeStyle='#e7ecf3';ctx.beginPath();ctx.arc(cx,cy,r,Math.PI,0);ctx.stroke();ctx.strokeStyle=p>90?'#d94c61':p>80?'#d89614':'#316fe9';ctx.beginPath();ctx.arc(cx,cy,r,Math.PI,Math.PI+Math.PI*p/100);ctx.stroke();ctx.fillStyle='#2c435f';ctx.font='700 17px Segoe UI';ctx.textAlign='center';ctx.fillText(`${p.toFixed(0)}%`,cx,cy-2)}
function drawResourceWave(canvas,pct){const z=prepCanvas(canvas);if(!z)return;const{ctx,w,h}=z;const p=Math.max(0,Math.min(100,Number(pct)||0)),level=h-(p/100)*h,phase=(Date.now()/350)%6.28;const g=ctx.createLinearGradient(0,0,0,h);g.addColorStop(0,'rgba(49,111,233,.48)');g.addColorStop(1,'rgba(49,111,233,.10)');ctx.beginPath();ctx.moveTo(0,h);ctx.lineTo(0,level);for(let x=0;x<=w;x+=3){const y=level+Math.sin(x/15+phase)*4;ctx.lineTo(x,y)}ctx.lineTo(w,h);ctx.closePath();ctx.fillStyle=g;ctx.fill();ctx.strokeStyle='#316fe9';ctx.lineWidth=2;ctx.beginPath();for(let x=0;x<=w;x+=3){const y=level+Math.sin(x/15+phase)*4;if(x===0)ctx.moveTo(x,y);else ctx.lineTo(x,y)}ctx.stroke();ctx.fillStyle='#29415e';ctx.font='700 15px Segoe UI';ctx.textAlign='center';ctx.fillText(`${p.toFixed(0)}%`,w/2,h/2+5)}
function drawResourceBar(canvas,pct){const z=prepCanvas(canvas);if(!z)return;const{ctx,w,h}=z,p=Math.max(0,Math.min(100,Number(pct)||0));const x=12,y=h*.36,bw=w-24,bh=14;ctx.fillStyle='#e8edf4';ctx.beginPath();ctx.roundRect(x,y,bw,bh,7);ctx.fill();ctx.fillStyle=p>90?'#d94c61':p>80?'#d89614':'#316fe9';ctx.beginPath();ctx.roundRect(x,y,bw*p/100,bh,7);ctx.fill();ctx.fillStyle='#2c435f';ctx.font='700 15px Segoe UI';ctx.textAlign='center';ctx.fillText(`${p.toFixed(0)}%`,w/2,y+bh+23)}
function drawResourceVisual(key,pct,history){const ring=$(`#${key}Ring`),viz=$(`#${key}Viz`);if(!ring||!viz)return;const type=chartType(`dashboard.${key.replace('context','context').replace('gpu0','gpu0').replace('gpu1','gpu1').replace('ram','ram')}`,'donut');if(type==='donut'){ring.classList.remove('hidden');viz.classList.add('hidden');return}ring.classList.add('hidden');viz.classList.remove('hidden');if(type==='gauge')drawGauge(viz,pct);else if(type==='wave')drawResourceWave(viz,pct);else if(type==='bar')drawResourceBar(viz,pct);else drawTrend(viz,(history||[]).map(x=>x.v),type,{compact:true,maxY:100})}
function pushHistory(key,v){const now=Date.now()/1000,a=state.resourceHistory[key];if(!a)return;if(!a.length||now-a.at(-1).ts>.35)a.push({ts:now,v:Number(v)||0});state.resourceHistory[key]=a.filter(x=>now-x.ts<900)}

function updateContextUI(){
  const c=activeContext(),used=Number(c.used||0),cap=Number(c.capacity||65536),pct=cap?used/cap*100:0,remain=Math.max(0,cap-used);
  $('#topContextValue').textContent=`${fmt.k(used)} / ${fmt.k(cap)}`;$('#topContextBar').style.width=`${Math.min(100,pct)}%`;$('#contextPct').textContent=`${pct.toFixed(0)}%`;$('#contextMain').textContent=`${fmt.k(used)} / ${fmt.k(cap)}`;$('#contextSub').textContent=`${fmt.k(remain)} remaining`;setRing($('#contextRing'),pct,pct>90?'var(--red)':pct>75?'var(--amber)':'var(--blue)');$('#chatContextValue').textContent=`${fmt.k(used)} / ${fmt.k(cap)}`;$('#chatContextBar').style.width=`${Math.min(100,pct)}%`;$('#chatContextRemain').textContent=`${fmt.k(remain)} remaining`;pushHistory('context',pct);drawResourceVisual('context',pct,state.resourceHistory.context);
}
function updateResources(gpus,sys){
  for(let i=0;i<2;i++){const g=gpus[i],ring=$(`#gpu${i}Ring`),pct=$(`#gpu${i}Pct`),main=$(`#gpu${i}Main`),sub=$(`#gpu${i}Sub`),card=$(`#gpu${i}Card`);if(!g){pct.textContent='—';main.textContent='GPU not found';sub.textContent='—';setRing(ring,0);drawResourceVisual(`gpu${i}`,0,[]);continue}const mp=Number(g.memory_percent||0);pct.textContent=`${mp.toFixed(0)}%`;main.textContent=`${fmt.n(g.memory_used_gb,1)} / ${fmt.n(g.memory_total_gb,1)} GB`;sub.textContent=`${g.name} · ${fmt.n(g.utilization,0)}% GPU · ${fmt.n(g.temperature_c,0)}°C · ${fmt.n(g.power_w,0)}W`;setRing(ring,mp,mp>92?'var(--red)':mp>82?'var(--amber)':'var(--blue)');card.querySelector('.resource-title').textContent=`GPU ${g.index} · ${g.name}`;pushHistory(`gpu${i}`,mp);drawResourceVisual(`gpu${i}`,mp,state.resourceHistory[`gpu${i}`])}
  const rp=Number(sys.ram_percent||0);$('#ramPct').textContent=`${rp.toFixed(0)}%`;$('#ramMain').textContent=`${fmt.n(sys.ram_used_gb,1)} / ${fmt.n(sys.ram_total_gb,1)} GB`;$('#ramSub').textContent=`CPU ${fmt.n(sys.cpu_percent,0)}%`;setRing($('#ramRing'),rp,rp>90?'var(--red)':rp>80?'var(--amber)':'var(--blue)');pushHistory('ram',rp);drawResourceVisual('ram',rp,state.resourceHistory.ram);
  $('#railHardware').innerHTML=(gpus.slice(0,2).map(g=>`<div class="hw-line"><span><b>${g.name}</b><em>${fmt.n(g.utilization,0)}% · ${fmt.n(g.memory_used_gb,1)}G</em></span><div class="mini-bar"><i style="width:${Math.min(100,g.memory_percent)}%"></i></div></div>`).join(''))+`<div class="hw-line"><span><b>RAM</b><em>${fmt.n(sys.ram_percent,0)}%</em></span><div class="mini-bar"><i style="width:${Math.min(100,sys.ram_percent||0)}%"></i></div></div>`;renderHardwareCards(gpus,sys);
}
function drawTps(){const now=Date.now()/1000,win=state.tpsWindow,samples=state.tpsSamples.filter(x=>now-x.ts<=win);$('#tpsEmpty').style.display=samples.length>1?'none':'grid';drawTrend($('#tpsChart'),samples.map(x=>x.v),chartType('dashboard.generation','wave'))}

function drawCategoryBars(canvas,items){const z=prepCanvas(canvas);if(!z)return;const{ctx,w,h}=z,arr=(items||[]).slice(0,7);if(!arr.length){drawEmptyCanvas(canvas);return}const max=Math.max(...arr.map(x=>Number(x.value)||0),1),left=Math.min(145,w*.42),top=12,row=Math.max(23,(h-20)/arr.length);ctx.font='9px Segoe UI';arr.forEach((it,i)=>{const y=top+i*row;ctx.fillStyle='#607188';ctx.textAlign='left';let label=String(it.label||'');if(label.length>22)label=label.slice(0,21)+'…';ctx.fillText(label,5,y+10);const bw=Math.max(2,(w-left-48)*(Number(it.value)||0)/max);ctx.fillStyle='#e8edf4';ctx.fillRect(left,y,w-left-45,10);ctx.fillStyle=palette(i);ctx.fillRect(left,y,bw,10);ctx.fillStyle='#596a80';ctx.textAlign='right';ctx.fillText(fmt.big(it.value),w-4,y+10)})}
function drawRuntimeStack(canvas,s){const z=prepCanvas(canvas);if(!z)return;const{ctx,w,h}=z,total=Math.max(1,Number(s.server_uptime_seconds||0)),active=Math.min(total,Number(s.inference_seconds||0)),idle=Math.max(0,total-active),x=18,y=h*.42,bw=w-36,bh=28;ctx.fillStyle='#e9edf3';ctx.beginPath();ctx.roundRect(x,y,bw,bh,8);ctx.fill();const aw=bw*active/total;ctx.fillStyle='#316fe9';ctx.beginPath();ctx.roundRect(x,y,aw,bh,8);ctx.fill();ctx.fillStyle='#9ab6e7';ctx.fillRect(x+aw,y,bw-aw,bh);ctx.font='9px Segoe UI';ctx.fillStyle='#425871';ctx.textAlign='left';ctx.fillText(`Inference ${fmt.hours(active)}`,x,y+bh+20);ctx.textAlign='right';ctx.fillText(`Idle-loaded ${fmt.hours(idle)}`,x+bw,y+bh+20)}

async function loadUsage(range=state.usageRange){try{state.usageRange=range;state.usage=await api(`/api/usage?range=${encodeURIComponent(range)}`);renderUsage()}catch(e){toast(e.message,'error')}}
function renderUsage(){const u=state.usage;if(!u)return;const s=u.summary||{};$('#usageKpis').innerHTML=[['Total Token',fmt.big(s.total_tokens),'Input + output'],['Input Token',fmt.big(s.prompt_tokens),'Prompt / context'],['Output Token',fmt.big(s.output_tokens),'Generated'],['Server Uptime',fmt.hours(s.server_uptime_seconds),'llama-server terdeteksi'],['Active Inference',fmt.hours(s.inference_seconds),`${s.requests||0} request`],['Avg Generation',s.avg_generation_tps?`${fmt.n(s.avg_generation_tps,2)} tok/s`:'—',`${s.models_used||0} model digunakan`]].map(x=>`<div class="usage-kpi"><span>${x[0]}</span><b>${x[1]}</b><small>${x[2]}</small></div>`).join('');$('#usageStreak').innerHTML=`<b>${s.current_streak_days||0} hari streak · ${s.longest_streak_days||0} terpanjang</b>${u.most_active_day?`${u.most_active_day.date} · ${fmt.big(u.most_active_day.total_tokens)} token`:'Belum ada aktivitas'}`;renderHeatmap(u.daily||[]);renderUsageCharts();renderUsageModels();renderUsageTimeline()}
function renderHeatmap(daily){const box=$('#usageHeatmap');const map=new Map(daily.map(x=>[x.date,x]));let start;if(state.usage?.period_start)start=new Date(state.usage.period_start);else if(daily.length)start=new Date(daily[0].date+'T00:00:00');else start=new Date();start.setHours(0,0,0,0);const end=new Date();end.setHours(0,0,0,0);const max=Math.max(1,...daily.map(x=>Number(x.total_tokens)||0)),offset=(start.getDay()+6)%7;let html='<i style="display:none"></i>';for(let i=0;i<offset;i++)html+='<span class="heat-cell" style="visibility:hidden"></span>';for(let d=new Date(start);d<=end;d.setDate(d.getDate()+1)){const key=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`,it=map.get(key),v=Number(it?.total_tokens||0),ratio=v?Math.sqrt(v/max):0,lvl=v?Math.max(1,Math.ceil(ratio*4)):0;html+=`<span class="heat-cell l${lvl}" data-tip="${key} · ${fmt.big(v)} token · ${it?.requests||0} request"></span>`}box.innerHTML=html}
function renderUsageCharts(){const u=state.usage||{},daily=u.daily||[],models=u.models||[],clients=u.clients||[],s=u.summary||{};const tokenType=chartType('usage.tokens','wave'),modelType=chartType('usage.models','bar'),clientType=chartType('usage.clients','donut');$('#usageTokenType').textContent=tokenType.toUpperCase();$('#usageModelType').textContent=modelType.toUpperCase();$('#usageClientType').textContent=clientType.toUpperCase();drawTrend($('#usageTokenChart'),daily.map(x=>x.total_tokens),tokenType);const mitems=models.slice(0,8).map(x=>({label:`${x.quantization||''} ${x.model_name||'Unknown'}`.trim(),value:x.total_tokens||0}));if(modelType==='donut')drawDonut($('#usageModelChart'),mitems);else if(modelType==='bar')drawCategoryBars($('#usageModelChart'),mitems);else drawTrend($('#usageModelChart'),mitems.map(x=>x.value),modelType);const citems=clients.map(x=>({label:x.client,value:x.total_tokens||0}));if(clientType==='donut')drawDonut($('#usageClientChart'),citems,fmt.big(s.total_tokens||0));else drawCategoryBars($('#usageClientChart'),citems);drawRuntimeStack($('#usageRuntimeChart'),s)}
function renderUsageModels(){const rows=state.usage?.models||[];$('#usageModelBody').innerHTML=rows.map(m=>`<tr><td class="model-usage-name" title="${escapeHtml(m.model_path||'')}"><b>${escapeHtml(m.quantization||'GGUF')}</b> · ${escapeHtml((m.model_name||'Unknown').slice(0,55))}</td><td>${fmt.hours(m.loaded_seconds)}</td><td>${fmt.hours(m.inference_seconds)}</td><td>${fmt.hours(m.idle_loaded_seconds)}</td><td>${fmt.big(m.prompt_tokens)}</td><td>${fmt.big(m.output_tokens)}</td><td>${fmt.big(m.total_tokens)}</td><td>${m.weighted_generation_tps?fmt.n(m.weighted_generation_tps,2):m.avg_generation_tps?fmt.n(m.avg_generation_tps,2):'—'}</td><td>${m.requests||0}</td></tr>`).join('')||'<tr><td colspan="9">Belum ada data model pada periode ini.</td></tr>'}
function renderUsageTimeline(){const arr=state.usage?.runtime_timeline||[];$('#usageTimeline').innerHTML=arr.map(x=>`<div class="runtime-entry"><div class="time">${fmt.time(x.started_at)}</div><div class="rail"></div><div class="body"><b>${escapeHtml(x.quantization||'GGUF')} · ${escapeHtml((x.model_name||'Unknown').slice(0,48))}</b><span>${fmt.hours(x.duration_seconds)} loaded · Context ${fmt.k(x.context_capacity||0)} · PID ${x.pid}${x.ended_at?' · stopped':' · running'}</span></div></div>`).join('')||'<div class="usage-empty">Belum ada runtime session yang tercatat.</div>'}
$$('#usageRange button').forEach(b=>b.onclick=()=>{$$('#usageRange button').forEach(x=>x.classList.toggle('active',x===b));loadUsage(b.dataset.range)});

function syncChartControls(){const d=state.chartConfig?.dashboard||{},u=state.chartConfig?.usage||{};const map={chartGeneration:d.generation,chartContext:d.context,chartGpu0:d.gpu0,chartGpu1:d.gpu1,chartRam:d.ram,chartUsageTokens:u.tokens,chartUsageModels:u.models,chartUsageClients:u.clients};Object.entries(map).forEach(([id,v])=>{const e=$(`#${id}`);if(e&&v)e.value=v});$$('.preset-card').forEach(x=>x.classList.toggle('active',x.dataset.preset===state.chartConfig?.preset))}
function readChartControls(){state.chartConfig.dashboard={...state.chartConfig.dashboard,generation:$('#chartGeneration').value,context:$('#chartContext').value,gpu0:$('#chartGpu0').value,gpu1:$('#chartGpu1').value,ram:$('#chartRam').value};state.chartConfig.usage={...state.chartConfig.usage,tokens:$('#chartUsageTokens').value,models:$('#chartUsageModels').value,clients:$('#chartUsageClients').value};state.chartConfig.preset='custom';$$('.preset-card').forEach(x=>x.classList.remove('active'));applyChartsNow();renderChartPreview()}
function applyPreset(name){const p=CHART_PRESETS[name];if(!p)return;state.chartConfig={preset:name,dashboard:clone(p.dashboard),usage:clone(p.usage)};syncChartControls();applyChartsNow();renderChartPreview();toast(`Preset ${name} diterapkan untuk preview`)}
function applyChartsNow(){if(state.telemetry){updateResources(state.telemetry.gpus||[],state.telemetry.system||{});updateContextUI()}drawTps();if(state.usage)renderUsageCharts()}
function renderChartPreview(){const demo=[22,38,31,54,47,68,61,76,64,82,74,88];drawTrend($('#previewGeneration'),demo,chartType('dashboard.generation','wave'),{compact:true});const drawPreviewResource=(id,type,pct,history)=>{const c=$(`#${id}`);if(type==='gauge')drawGauge(c,pct);else if(type==='donut')drawDonut(c,[{value:pct},{value:100-pct}],`${pct}%`);else if(type==='wave')drawResourceWave(c,pct);else if(type==='bar')drawResourceBar(c,pct);else drawTrend(c,history,type,{compact:true,maxY:100})};drawPreviewResource('previewContext',chartType('dashboard.context','gauge'),58,[19,25,31,38,42,49,58]);drawPreviewResource('previewGpu0',chartType('dashboard.gpu0','wave'),72,[28,55,41,68,80,66,72]);drawPreviewResource('previewRam',chartType('dashboard.ram','bar'),49,[42,43,47,46,49,48,49])}
$$('.preset-card').forEach(b=>b.onclick=()=>applyPreset(b.dataset.preset));['chartGeneration','chartContext','chartGpu0','chartGpu1','chartRam','chartUsageTokens','chartUsageModels','chartUsageClients'].forEach(id=>{const e=$(`#${id}`);if(e)e.onchange=readChartControls});
$('#saveChartsBtn').onclick=async()=>{try{await api('/api/config',{method:'POST',body:JSON.stringify({charts:state.chartConfig})});state.settings=state.settings||{};state.settings.charts=clone(state.chartConfig);toast('Visualization saved','success')}catch(e){toast(e.message,'error')}};

function connectWS(){ if(state.ws){try{state.ws.close()}catch{}} const proto=location.protocol==='https:'?'wss':'ws';const ws=new WebSocket(`${proto}://${location.host}/ws/telemetry`);state.ws=ws;ws.onmessage=e=>{try{updateTelemetry(JSON.parse(e.data))}catch(err){console.warn(err)}};ws.onclose=()=>setTimeout(connectWS,1800);ws.onerror=()=>ws.close(); }

(async function init(){
  const page=(location.hash||'#dashboard').slice(1);go(document.getElementById(`page-${page}`)?page:'dashboard');
  await refreshStatus();await loadSettings();await loadSessions();await loadModels();await loadHistory();await loadUsage(state.usageRange);connectWS();
  setInterval(()=>{if(state.page==='server')refreshServerLog()},4000);
})();


