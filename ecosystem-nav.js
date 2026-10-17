'use strict';
(() => {
  let apps = {};
  let polling = false;
  const labels = {online:'Online',offline:'Offline',outdated:'Versi / instalasi berbeda',conflict:'Konflik port',unknown:'Status belum tersedia'};
  function message(text) {
    let box = document.getElementById('ecosystem-notice');
    if (!box) {
      box = document.createElement('div'); box.id='ecosystem-notice'; box.className='eco-notice';
      box.setAttribute('role','status'); box.setAttribute('aria-live','polite');
      const content=document.createElement('span'); content.id='ecosystem-notice-text';
      const close=document.createElement('button');close.textContent='Tutup';close.onclick=()=>box.hidden=true;
      box.append(content,close);document.body.append(box);
    }
    document.getElementById('ecosystem-notice-text').textContent=text;box.hidden=false;
  }
  function update() {
    document.querySelectorAll('[data-ecosystem-app]').forEach(link => {
      const app = apps[link.dataset.ecosystemApp];
      const state=app?.state||'unknown';
      link.href=app?.url||'#';link.dataset.ecosystemState=state;
      link.setAttribute('aria-disabled',String(!app?.compatible));
      const status=(labels[state]||state)+(app?.compatible&&!app.ready?' · Menyiapkan sensor':'')+(app?.demo?' · DEMO':'');
      link.title=(app?.name||link.textContent.trim())+' · '+status+(app?.version?' · v'+app.version:'');
      const indicator=link.querySelector('.bridge-state,.bridge-status,.dot');
      if(indicator){indicator.classList.toggle('online',!!app?.compatible);indicator.classList.toggle('offline',!app?.compatible);indicator.title=status;indicator.setAttribute('aria-label',status)}
      let badge=link.querySelector('.eco-state');
      if(!badge){badge=document.createElement('small');badge.className='eco-state';link.append(badge)}
      badge.textContent=status;
    });
  }
  async function poll() {
    if(polling)return;polling=true;
    try {
      const endpoint=location.pathname==='/'&&document.getElementById('app-counter')?'/api/apps':'/api/ecosystem/apps';
      const response=await fetch(endpoint,{cache:'no-store',signal:AbortSignal.timeout(4500)});
      if(!response.ok)throw Error('HTTP '+response.status);
      const data=await response.json();apps=data.apps;
      window.dispatchEvent(new CustomEvent('ecosystem-status',{detail:data}));
    } catch { apps={};window.dispatchEvent(new Event('ecosystem-status-error')); }
    finally {polling=false;update()}
  }
  document.addEventListener('click',event=>{
    const link=event.target.closest('[data-ecosystem-app]');if(!link)return;
    const app=apps[link.dataset.ecosystemApp];
    if(!app?.compatible){
      event.preventDefault();
      message(`${app?.name||'Layanan'}: ${labels[app?.state||'unknown']}. ${app?.state==='outdated'||app?.state==='conflict'?'Tutup proses pemilik atau instalasi lama, lalu jalankan START-EKOSISTEM.bat.':'Jalankan START-EKOSISTEM.bat dari folder ekosistem, lalu periksa ulang.'}`);
      poll();
    }
  });
  poll();setInterval(poll,12000);
})();
