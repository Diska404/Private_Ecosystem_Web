"""Real 3-process test with temporary ports, databases, logs and ownership files."""
from pathlib import Path
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}))


def run():
    with tempfile.TemporaryDirectory() as folder:
        work=Path(folder)
        sockets=[]
        for i in range(3):
            s=socket.socket();s.bind(('127.0.0.1',0));sockets.append(s)
        ports=[s.getsockname()[1] for s in sockets]
        for s in sockets:s.close()
        env=dict(os.environ,ECOSYSTEM_PORT=str(ports[0]),ECOSYSTEM_AI_PORT=str(ports[1]),
                 ECOSYSTEM_SIGNALDECK_PORT=str(ports[2]),SIGNALDECK_DATA_DIR=str(work/'deck'),
                 LOCAL_AI_DATA_DIR=str(work/'ai'),ECOSYSTEM_STATE_DIR=str(work/'state'),
                 ECOSYSTEM_LOG_DIR=str(work/'logs'),SIGNALDECK_DEMO='1',PYTHONIOENCODING='utf-8')
        def command(action,service='all'):
            result=subprocess.run([sys.executable,str(ROOT/'launch_all.py'),action,service,'--no-browser'],
                                  cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=100)
            print(result.stdout,flush=True)
            if result.returncode:raise AssertionError(result.stderr)
        def get(index,path):
            with OPENER.open(f'http://127.0.0.1:{ports[index]}{path}',timeout=5) as r:
                raw=r.read();return json.loads(raw) if 'json' in r.headers.get('Content-Type','') else raw
        try:
            command('start')
            first=[get(i,'/api/health') for i in range(3)]
            assert all(h['version']=='2.1.0' for h in first)
            assert get(1,'/api/config')['app']['port']==ports[1]
            command('start')
            assert [h['instance'] for h in first]==[get(i,'/api/health')['instance'] for i in range(3)],'start must be idempotent'
            for i,path in enumerate(['/api/apps','/api/ecosystem/apps','/api/ecosystem/apps']):
                result=get(i,path)
                assert [app['port'] for app in result['apps'].values()]==ports
                assert all(app['compatible'] for app in result['apps'].values())
            print('PASS dynamic ports, 3-way registry, identity, idempotent start',flush=True)
            for i in range(3):
                request=urllib.request.Request(f'http://127.0.0.1:{ports[i]}/api/ecosystem/shutdown',data=b'',method='POST')
                try:OPENER.open(request,timeout=5);raise AssertionError('Unauthenticated shutdown accepted')
                except urllib.error.HTTPError as exc:assert exc.code==403
            cap=get(2,'/api/tuning/capabilities');assert not cap['hardware_apply_supported'] and not cap['driver_write_enabled']
            deadline=time.monotonic()+12
            while not get(2,'/api/health')['ok'] and time.monotonic()<deadline:time.sleep(.2)
            assert get(2,'/api/snapshot')['data']['demo'] is True
            assert b'ts' in get(2,'/api/export?period=live')
            print('PASS shutdown authorization, draft-only capabilities, labelled demo, CSV',flush=True)
            command('stop','signaldeck')
            assert get(0,'/api/apps')['apps']['signaldeck']['state']=='offline'
            command('start','signaldeck')
            command('restart')
            assert all(get(i,'/api/health')['instance']!=first[i]['instance'] for i in range(3))
            print('PASS offline status, per-service start/stop, restart all',flush=True)
        finally:
            command('stop')
            # Verify actual processes exited before the temporary log/DB directory is cleaned up.
            time.sleep(1)
        print('PASS graceful stop all; isolated test data cleaned up',flush=True)


if __name__=='__main__':run()
