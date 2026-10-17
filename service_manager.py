"""Owned service lifecycle. No PID killing and no takeover of foreign processes."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.request
import webbrowser
from ecosystem import ROOT, VERSION, OPENER, registry, probe

from pathlib import Path
STATE = Path(os.environ.get('ECOSYSTEM_STATE_DIR', ROOT / '.ecosystem'))
LOGS = Path(os.environ.get('ECOSYSTEM_LOG_DIR', ROOT / 'logs'))


@contextmanager
def manager_lock():
    STATE.mkdir(exist_ok=True)
    with (STATE / 'manager.lock').open('a+b') as handle:
        handle.seek(0); handle.write(b'0'); handle.flush(); handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('Pengelola layanan lain sedang bekerja; coba lagi sesudah selesai.') from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def read_owner(key):
    try:
        return json.loads((STATE / f'{key}.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_owner(key, data):
    target = STATE / f'{key}.json'
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2), encoding='utf-8')
    temporary.replace(target)


def python_for(key):
    if key == 'hub':
        return sys.executable
    folder = ROOT / ('local-ai-control-center' if key == 'ai' else 'SignalDeck-Hardware-Monitor')
    executable = folder / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not executable.exists():
        subprocess.run([sys.executable, '-m', 'venv', str(folder / '.venv')], check=True)
    modules = 'fastapi,uvicorn,httpx,psutil,pynvml' if key == 'ai' else 'psutil,pynvml'
    if subprocess.run([str(executable), '-c', f'import {modules}'], capture_output=True).returncode:
        print(f'[SETUP] Dependency {key}: koneksi internet mungkin diperlukan.', flush=True)
        subprocess.run([str(executable), '-m', 'pip', 'install', '-r', str(folder / 'requirements.txt')], check=True)
    return str(executable)


def start_service(key, item, items):
    owner = read_owner(key)
    if owner.get('url') and owner['url'] != item['url']:
        from urllib.parse import urlsplit
        previous = urlsplit(owner['url'])
        if previous.hostname != '127.0.0.1' or previous.scheme != 'http' or not previous.port:
            raise RuntimeError('Alamat ownership tidak valid')
        if probe({**item,'url':owner['url'],'port':previous.port})['state'] != 'offline':
            raise RuntimeError(f'{key}: instance pada port sebelumnya masih aktif. Jalankan stop sebelum start dengan port baru.')
    current = probe(item)
    if current['state'] == 'online':
        print(f'[OK] {key}: {item["url"]} v{current["version"]}')
        return
    if current['state'] != 'offline':
        raise RuntimeError(f'{key}: port {item["port"]} {current["state"]}. Tutup proses pemilik secara manual.')
    python = python_for(key)
    if probe(item)['state'] != 'offline':
        raise RuntimeError(f'{key}: port berubah saat persiapan; jalankan status.')
    token, instance = secrets.token_urlsafe(32), secrets.token_hex(16)
    env = dict(os.environ, ECOSYSTEM_CONTROL_TOKEN=token, ECOSYSTEM_INSTANCE=instance,
               ECOSYSTEM_PORT=str(items['hub']['port']), ECOSYSTEM_AI_PORT=str(items['ai']['port']),
               ECOSYSTEM_SIGNALDECK_PORT=str(items['signaldeck']['port']),
               SIGNALDECK_PORT=str(items['signaldeck']['port']),
               SIGNALDECK_BROWSER='0', LOCAL_AI_NO_BROWSER='1', PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8')
    if key == 'hub':
        command, cwd = [python, str(ROOT / 'ecosystem_hub.py')], ROOT
    elif key == 'ai':
        command, cwd = [python, '-m', 'backend.main'], ROOT / 'local-ai-control-center'
    else:
        command, cwd = [python, 'app.py'], ROOT / 'SignalDeck-Hardware-Monitor'
    LOGS.mkdir(exist_ok=True)
    logfile = LOGS / f'{key}.log'
    with logfile.open('ab') as log:
        log.write(f'\n--- {time.strftime("%Y-%m-%d %H:%M:%S")} start {VERSION} ---\n'.encode()); log.flush()
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=log,
                                   stdin=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                                   start_new_session=os.name != 'nt')
    save_owner(key, {'pid': process.pid, 'instance': instance, 'token': token, 'url': item['url'],
                     'started': time.time(), 'log': str(logfile)})
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        health = probe(item)
        if health['compatible'] and health['health'].get('instance') == instance:
            actual_pid = health['health']['pid']
            save_owner(key, {'pid': actual_pid, 'launcher_pid': process.pid, 'instance': instance,
                             'token': token, 'url': item['url'], 'started': time.time(), 'log': str(logfile)})
            print(f'[START] {key}: PID {actual_pid} | {item["url"]} | log: {logfile}', flush=True)
            return
        if process.poll() is not None:
            raise RuntimeError(f'{key} berhenti (exit {process.returncode}); lihat {logfile}')
        time.sleep(.3)
    raise RuntimeError(f'{key} belum merespons setelah 35 detik; proses tidak dipaksa berhenti. Lihat {logfile}')


def stop_service(key, item):
    owner = read_owner(key)
    target = dict(item)
    if owner.get('url'):
        from urllib.parse import urlsplit
        parsed = urlsplit(owner['url'])
        if parsed.hostname != '127.0.0.1' or parsed.scheme != 'http' or not parsed.port:
            raise RuntimeError('Alamat ownership tidak valid')
        target.update(url=owner['url'], port=parsed.port)
    current = probe(target)
    if current['state'] == 'offline':
        print(f'[OFF] {key}')
        return
    info = current.get('health') or {}
    if not (current['compatible'] and owner.get('instance') and
            info.get('instance') == owner['instance']):
        raise RuntimeError(f'{key}: bukan instance milik launcher ini. Tidak dihentikan; tutup terminal pemilik.')
    request = urllib.request.Request(target['url'] + 'api/ecosystem/shutdown', data=b'', method='POST',
                                     headers={'X-Ecosystem-Token': owner['token']})
    with OPENER.open(request, timeout=5) as response:
        if response.status != 202:
            raise RuntimeError(f'{key}: shutdown ditolak')
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        state = probe(target)
        if state['state'] == 'offline':
            (STATE / f'{key}.json').unlink(missing_ok=True)
            print(f'[STOP] {key}: shutdown normal')
            return
        if (state.get('health') or {}).get('instance') != owner['instance']:
            raise RuntimeError(f'{key}: pemilik port berubah saat shutdown; tidak disentuh.')
        time.sleep(.25)
    raise RuntimeError(f'{key}: shutdown belum selesai. Periksa log; tidak memakai force-kill.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', nargs='?', default='start', choices=['start','status','stop','restart','open','logs'])
    parser.add_argument('service', nargs='?', default='all', choices=['all','hub','ai','signaldeck'])
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args(argv)
    items = registry()
    keys = list(items) if args.service == 'all' else [args.service]
    print(f'LOCAL WORK & SETTING v{VERSION}', flush=True)
    if args.action == 'open':
        webbrowser.open(items['hub' if args.service == 'all' else args.service]['url']); return 0
    if args.action == 'status':
        for key in keys:
            state = probe(items[key]); info = state.get('health') or {}; owner = read_owner(key)
            managed = bool(info.get('instance') and info.get('instance') == owner.get('instance'))
            print(f'{key:12} {state["state"]:10} {items[key]["url"]} v{state["version"] or "N/A"} PID={info.get("pid", "N/A")} managed={managed} ready={state["ready"]}')
        return 0
    if args.action == 'logs':
        for key in keys:
            path = LOGS / f'{key}.log'; print(f'[{key}] {path}')
            if path.exists():
                with path.open('rb') as handle:
                    handle.seek(max(0, path.stat().st_size - 16000))
                    print(handle.read().decode('utf-8', 'replace'))
        return 0
    with manager_lock():
        if args.action in ('stop','restart'):
            for key in reversed(keys):
                stop_service(key, items[key])
        if args.action in ('start','restart'):
            for key in keys:
                state = probe(items[key])
                if state['state'] not in ('online','offline'):
                    raise RuntimeError(f'{key}: {state["state"]} di port {items[key]["port"]}; tidak mengambil alih proses.')
            for key in keys:
                start_service(key, items[key], items)
            if not args.no_browser:
                webbrowser.open(items['hub' if args.service == 'all' else args.service]['url'])
    return 0


def entrypoint():
    try:
        return main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f'[ERROR] {exc}', file=sys.stderr); return 1
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(entrypoint())
