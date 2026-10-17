const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

function studio(saved={}) {
  const events={},nodes=new Map(),storage=new Map(Object.entries(saved));
  const document={
    addEventListener:(name,fn)=>(events[name]??=[]).push(fn),
    getElementById:id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',innerHTML:'',dataset:{},value:''});return nodes.get(id)},
    querySelector:()=>null,
  };
  const context={window:{},document,location:{hash:'#tuning'},structuredClone,console,AbortSignal,
    localStorage:{getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value)},
    fetch:()=>Promise.resolve({ok:true,json:()=>Promise.resolve({hardware_apply_supported:false})})};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../SignalDeck-Hardware-Monitor/static/tuning.js'),'utf8'),context);
  const snapshot={demo:false,cpu:{name:'CPU'},gpus:[{id:'nvidia-0',stable_id:'UUID-A',name:'GPU A',vendor:'NVIDIA'},{id:'nvidia-1',stable_id:'UUID-B',name:'GPU B',vendor:'NVIDIA'}]};
  const render=()=>context.window.SignalTuning.render(snapshot);
  render();
  const fire=async(type,target)=>{target.closest??=()=>null;for(const fn of events[type]||[])await fn({target,detail:1})};
  const click=id=>fire('click',{id});
  const input=(key,value)=>fire('input',{dataset:{tune:key},value});
  const profile=()=>JSON.parse(storage.get('signaldeck.tuning.profiles.v2'))['gpu:UUID-A'];
  return {context,nodes,storage,render,fire,click,input,profile};
}

test('unsaved changes survive navigation and undo restores the prior value',async()=>{
  const s=studio();await s.input('power',90);s.render();await s.click('save-tune');assert.equal(s.profile().power,90);
  await s.click('undo-tune');await s.click('save-tune');assert.equal(s.profile().power,85);
});

test('curve edits clamp to adjacent values and remain monotonic',async()=>{
  const s=studio();await s.fire('input',{dataset:{fanIndex:'2'},value:'99'});await s.click('save-tune');
  assert.deepEqual(s.profile().fanpoints,[25,35,68,68,85]);
  await s.fire('input',{dataset:{vfIndex:'2'},value:'1000'});await s.click('save-tune');
  assert.deepEqual(s.profile().corecurve,[1800,1950,1950,2250,2380]);
});

test('profiles use UUID identity and never auto-assign an ambiguous legacy index',async()=>{
  const legacy={'gpu:nvidia-0':{power:99}};
  const s=studio({'signaldeck.tuning.profiles.v2':JSON.stringify(legacy)});await s.click('save-tune');
  assert.equal(s.profile().power,85);
  assert.equal(JSON.parse(s.storage.get('signaldeck.tuning.profiles.v2'))['gpu:nvidia-0'].power,99);
});

test('invalid import is rejected without changing the draft',async()=>{
  const s=studio();await s.click('save-tune');const original=s.profile();
  const invalid={format:'signaldeck-tuning-draft-v2',device:'gpu:UUID-A',profile:{...original,fanpoints:[90,30,40,50,60]}};
  await s.fire('change',{id:'import-tune-file',files:[{size:1000,text:async()=>JSON.stringify(invalid)}]});
  assert.match(s.nodes.get('tune-message').textContent,/Impor gagal/);
  await s.click('save-tune');assert.deepEqual(s.profile(),original);
});

test('valid import can be saved and reset can be undone',async()=>{
  const s=studio();await s.click('save-tune');const original=s.profile();
  const valid={format:'signaldeck-tuning-draft-v2',device:'gpu:UUID-A',profile:{...original,power:95}};
  await s.fire('change',{id:'import-tune-file',files:[{size:1000,text:async()=>JSON.stringify(valid)}]});
  await s.click('save-tune');assert.equal(s.profile().power,95);
  await s.click('reset-tune');await s.click('undo-tune');await s.click('save-tune');assert.equal(s.profile().power,95);
});

test('storage errors are reported and hardware apply stays disabled',async()=>{
  const s=studio();s.context.localStorage.setItem=()=>{throw Error('quota')};await s.click('save-tune');
  assert.match(s.nodes.get('tune-message').textContent,/Gagal menyimpan/);
  assert.match(s.render(),/disabled[^>]*>Apply to Hardware/);
});
