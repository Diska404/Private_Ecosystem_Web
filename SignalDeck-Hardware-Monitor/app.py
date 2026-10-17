"""SignalDeck HTTP service â€” local-only, Python standard library (no web framework)."""
from __future__ import annotations
import json
import mimetypes
import os
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ecosystem import registry, apps_status, identity, authorized_shutdown

from collector import HardwareCollector
from storage import HistoryStore, PERIODS

ROOT=Path(__file__).resolve().parent
STATIC=(ROOT/'static').resolve()
DEMO=os.environ.get('SIGNALDECK_DEMO','0')=='1'
PORT=registry()['signaldeck']['port']
state={'snapshot':None,'error':None,'last_updated':None}
state_lock=threading.RLock()
store=HistoryStore(Path(os.environ.get('SIGNALDECK_DATA_DIR',ROOT/'data'))/('demo_history.db' if DEMO else 'history.db'))
collector=None
STOP=threading.Event()
worker=None


def sampler():
    global collector
    try:
        collector=HardwareCollector(demo=DEMO)
    except Exception as exc:
        with state_lock:
            state['error']=f'Inisialisasi kolektor gagal: {type(exc).__name__}: {exc}'
        return
    peaks={}
    while not STOP.is_set():
        start=time.monotonic()
        try:
            snapshot=collector.collect()
            values={'cpu':snapshot['cpu'].get('usage_percent'),
                    'cpu_temp':snapshot['cpu'].get('temperature_c'),
                    'ram':snapshot['memory'].get('percent')}
            for gpu in snapshot.get('gpus',[]):
                values[f"gpu.{gpu['id']}.load"]=gpu.get('usage_percent')
                values[f"gpu.{gpu['id']}.temp"]=gpu.get('temperature_c')
                values[f"gpu.{gpu['id']}.vram"]=gpu.get('memory_percent')
            for key,val in values.items():
                if isinstance(val,(int,float)):
                    peaks[key]=max(peaks.get(key,float('-inf')),val)
            snapshot['session_peaks']=dict(peaks)
            snapshot['session_started']=collector.started
            with state_lock:
                state.update(snapshot=snapshot,error=None,last_updated=time.time())
            store.record(snapshot)
        except Exception as exc:
            with state_lock:
                state['error']=f'{type(exc).__name__}: {exc}'
        STOP.wait(max(0.3,2.0-(time.monotonic()-start)))


class Handler(BaseHTTPRequestHandler):
    server_version='SignalDeck/2.1.0'

    def do_GET(self):
        parsed=urllib.parse.urlsplit(self.path)
        path=parsed.path
        args=urllib.parse.parse_qs(parsed.query)
        if path=='/api/snapshot':
            with state_lock:
                current=state['snapshot']
                error=state['error']
            if current is None:
                return self.send_json({'ok':False,'waiting':True,'error':error},503)
            return self.send_json({'ok':True,'data':current,'error':error})
        if path=='/api/health':
            with state_lock:
                current={'ok':state['snapshot'] is not None,'error':state['error'],
                         'last_updated':state['last_updated'],'demo':DEMO,**identity('signaldeck'),
                         'sampler_alive':worker.is_alive() if worker else False}
            return self.send_json(current)
        if path=='/api/ecosystem/apps': return self.send_json(apps_status())
        if path in ('/ecosystem-nav.js','/ecosystem-nav.css'):
            target=ROOT.parent/path.lstrip('/')
            return self.send_body(target.read_bytes(),'text/javascript; charset=utf-8' if target.suffix=='.js' else 'text/css; charset=utf-8')
        if path=='/api/tuning/capabilities':
            with state_lock:
                snap=state['snapshot']
            devices=[{'id':'cpu','name':snap.get('cpu',{}).get('name','CPU'),'type':'cpu'}] if snap else []
            for gpu in (snap or {}).get('gpus',[]):
                devices.append({'id':'gpu:'+str(gpu.get('stable_id') or gpu.get('id')),
                    'telemetry_id':gpu.get('id'),'name':gpu.get('name','GPU'),'type':'gpu',
                    'source':gpu.get('source'), 'stable_identity':bool(gpu.get('stable_id')),
                    'readable_metrics':[key for key in ('usage_percent','temperature_c','power_w','power_limit_w','clock_mhz','memory_clock_mhz','fan_percent') if gpu.get(key) is not None]})
            for device in devices:
                device.update(write_supported=False, driver_ranges=None,
                    reason='Adapter tulis belum terverifikasi; rentang editor bukan batas driver.')
            return self.send_json({'status':'profile_editor_only','driver_write_enabled':False,
                'hardware_apply_supported':False,'reason':'No verified vendor-specific tuning adapter/rollback',
                'devices':devices})
        if path=='/api/bridge':
            data=apps_status()['apps']
            return self.send_json({'hub':data['hub'],'local_ai':data['ai']})
        if path=='/api/history':
            period=args.get('period',['live'])[0]
            if period not in PERIODS:
                return self.send_json({'error':'Periode tidak valid'},400)
            return self.send_json(store.get_history(period))
        if path=='/api/export':
            period=args.get('period',['24h'])[0]
            if period not in PERIODS:
                return self.send_json({'error':'Periode tidak valid'},400)
            raw=store.export_csv(period).encode('utf-8-sig')
            return self.send_body(raw,content_type='text/csv; charset=utf-8',
                                  additional={'Content-Disposition':f'attachment; filename="signaldeck-{period}.csv"'})
        if path=='/': path='/static/index.html'
        if not path.startswith('/static/'):
            return self.send_json({'error':'Not found'},404)
        filename=(STATIC/path[len('/static/'):]).resolve()
        if not filename.is_relative_to(STATIC) or not filename.is_file():
            return self.send_json({'error':'Not found'},404)
        body=filename.read_bytes()
        content_type=mimetypes.guess_type(filename.name)[0] or 'application/octet-stream'
        if filename.suffix in ('.html','.js','.css','.svg'):
            content_type+='; charset=utf-8'
        self.send_body(body,content_type)

    def do_POST(self):
        if self.path=='/api/ecosystem/shutdown':
            if not authorized_shutdown(self.headers): return self.send_json({'error':'Launcher ownership required'},403)
            self.send_json({'ok':True},202)
            threading.Thread(target=self.server.shutdown,daemon=True).start()
            return
        self.send_json({'error':'Read-only service'},405)

    def send_json(self,obj,status=200):
        self.send_body(json.dumps(obj,allow_nan=False,separators=(',',':')).encode('utf-8'),
                       'application/json; charset=utf-8',status)

    def send_body(self,data,content_type,status=200,additional=None):
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; font-src 'self'")
        for key,value in (additional or {}).items(): self.send_header(key,value)
        self.end_headers()
        try: self.wfile.write(data)
        except (ConnectionError,BrokenPipeError): pass

    def log_message(self,format,*args):
        if not self.path.startswith('/api/snapshot') and not self.path.startswith('/api/health'):
            super().log_message(format,*args)


def start_worker():
    global worker
    if worker is None or not worker.is_alive():
        worker=threading.Thread(target=sampler,name='signaldeck-collector',daemon=True)
        worker.start()


def main():
    start_worker()
    url=f'http://127.0.0.1:{PORT}'
    print(f'\n  SignalDeck Hardware Monitor 2.0 | {url}')
    print('  Mode:', 'SIMULASI (tidak membaca sensor nyata)' if DEMO else 'Sensor nyata')
    print('  Ctrl+C untuk menghentikan server.\n')
    if os.environ.get('SIGNALDECK_BROWSER','1')!='0':
        threading.Thread(target=lambda:(time.sleep(1.3),webbrowser.open(url)),daemon=True).start()
    # Binding to loopback ensures telemetry is not exposed on LAN.
    try:
        httpd=ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
        httpd.serve_forever(poll_interval=.5)
    except OSError as exc:
        print('[ERROR] Tidak dapat membuka port 127.0.0.1:',PORT,exc)
        raise SystemExit(1)
    except KeyboardInterrupt:
        print('\nMenghentikan SignalDeck...')
    finally:
        STOP.set()
        if worker: worker.join(timeout=10)
        if 'httpd' in locals(): httpd.server_close()


if __name__=='__main__':
    main()
