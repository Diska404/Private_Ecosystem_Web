'use strict';
const $=id=>document.getElementById(id);
const statuses=['ai','deck'];
function renderServices(data){
 try {
  let up=0;
  for(const [key,id] of [['ai','ai'],['signaldeck','deck']]){
   const app=data.apps[key],running=app.compatible; if(running)up++;
   $('card-'+id).href=app.url;$('side-'+id).href=app.url;$('address-'+id).textContent=new URL(app.url).host;
   for(const sid of ['status-'+id,'row-'+id]){const el=$(sid);el.className='status '+(running?'online':'offline');el.textContent=running?'ONLINE':'OFFLINE';}
   $('dot-'+id).className='dot '+(running?'online':'offline');
   const outdated=app.state==='outdated';
   $('detail-'+id).textContent=running?(outdated?'Versi lama terdeteksi · restart instalasi lama':'Versi '+app.version+' · PID '+app.health?.pid+(app.ready?' · Ready':' · Menyiapkan sensor')+(app.demo?' · DEMO':'')):outdated?'Versi / instalasi berbeda · tutup proses pemilik':app.state==='conflict'?'Konflik port · proses lain memakai port ini':'Tidak berjalan · jalankan START-EKOSISTEM.bat';
   $('card-'+id).classList.toggle('dimmed',!running);
  }
  $('app-counter').textContent=`${up} / 2 aplikasi online`;
 } catch(err){$('app-counter').textContent='Status tidak tersedia: '+err.message}
}
window.addEventListener('ecosystem-status',event=>renderServices(event.detail));
window.addEventListener('ecosystem-status-error',()=>{
 $('app-counter').textContent='Status layanan tidak tersedia · periksa koneksi ke Hub';
 for(const id of ['ai','deck']){
  for(const sid of ['status-'+id,'row-'+id]){$(sid).className='status';$(sid).textContent='UNKNOWN'}
  $('detail-'+id).textContent='Pemeriksaan status gagal; muat ulang setelah backend pulih.';
 }
});
$('refresh').addEventListener('click',()=>location.reload());
