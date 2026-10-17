"""One user-facing BAT for the existing ecosystem and the local DevPulse preview."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent.parent
ECOSYSTEM = ROOT / 'Ecosystem v2.0'
DEVPULSE = ROOT / 'DevWev Portofolio'
sys.path.insert(0, str(ECOSYSTEM))
from ecosystem import registry, probe, occupied
import service_manager

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def devpulse_url():
    manifest = json.loads((DEVPULSE / 'apps/web/package.json').read_text(encoding='utf-8-sig'))
    command = manifest['scripts']['dev']
    port = re.search(r'--port\s+(\d+)\b', command)
    if not port or not re.search(r'--hostname\s+127\.0\.0\.1\b', command):
        raise RuntimeError('Script dev DevPulse harus menentukan --hostname 127.0.0.1 dan --port.')
    number = int(port[1])
    if not 1024 <= number <= 65535:
        raise RuntimeError('Port DevPulse tidak valid.')
    return f'http://127.0.0.1:{number}/', number


def devpulse_status(url, port):
    """Identify the existing prototype through two read-only responses, without takeover."""
    try:
        with OPENER.open(url, timeout=1.5) as response:
            html = response.read(512_000).decode('utf-8', 'replace')
        if not re.search(r'<title[^>]*>[^<]*DevPulse', html, re.I):
            return 'conflict'
        try:
            OPENER.open(url + 'api/owner/_launcher-check', timeout=1.5).close()
            return 'conflict'
        except urllib.error.HTTPError as response:
            try:
                error = json.loads(response.read(8192))
                return 'online' if response.code == 401 and isinstance(error, dict) and error.get('error') == 'unauthenticated' else 'conflict'
            finally:
                response.close()
    except (OSError, ValueError, TypeError):
        return 'conflict' if occupied(port) else 'offline'


def check_node():
    node = shutil.which('node.exe') or shutil.which('node')
    if not node or not shutil.which('npm.cmd'):
        raise RuntimeError('Node.js dan npm diperlukan untuk DevPulse. Pasang Node.js 20.9+ lalu buka ulang launcher.')
    result = subprocess.run([node, '--version'], capture_output=True, text=True, check=True)
    version = tuple(int(part) for part in result.stdout.strip().lstrip('v').split('.')[:2])
    if version < (20, 9):
        raise RuntimeError('DevPulse memerlukan Node.js 20.9 atau lebih baru.')


def start_devpulse(url, port):
    state = devpulse_status(url, port)
    if state == 'online':
        print(f'[OK] DevPulse sudah berjalan: {url}', flush=True)
        return
    if state != 'offline':
        raise RuntimeError(f'Port {port} ditempati layanan yang tidak dikenali sebagai DevPulse. Tidak diambil alih.')
    check_node()
    if not (DEVPULSE / 'node_modules/next/dist/bin/next').is_file() and not (ROOT / 'node_modules/next/dist/bin/next').is_file():
        print('[SETUP] Memasang dependency DevPulse dari package-lock.json; internet mungkin diperlukan.', flush=True)
        subprocess.run([os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', 'npm.cmd', 'ci'], cwd=DEVPULSE, check=True)
    if devpulse_status(url, port) != 'offline':
        raise RuntimeError('Status port DevPulse berubah selama persiapan. Jalankan launcher kembali.')
    subprocess.Popen([os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', '.web-launcher\\RUN-DEVPULSE.bat'],
                     cwd=ROOT, creationflags=subprocess.CREATE_NEW_CONSOLE)
    print('[START] DevPulse sedang dimulai di terminal DevPulse. Tunggu sampai siap...', flush=True)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if devpulse_status(url, port) == 'online':
            print(f'[READY] DevPulse: {url}', flush=True)
            return
        time.sleep(1)
    raise RuntimeError('DevPulse belum siap dalam 120 detik. Periksa terminal DevPulse; proses tidak dipaksa berhenti.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-browser', action='store_true', help='Start/check without opening browser tabs')
    parser.add_argument('--status', action='store_true', help='Only inspect all four services')
    args = parser.parse_args(argv)
    if sys.platform != 'win32':
        raise RuntimeError('Launcher BAT gabungan ini khusus Windows.')
    services = registry()
    url, port = devpulse_url()
    if port in {item['port'] for item in services.values()}:
        raise RuntimeError('Port DevPulse harus berbeda dari port ketiga aplikasi ekosistem.')
    print('PRIVATE WEB - ECOSYSTEM + DEVPULSE', flush=True)
    if args.status:
        for key, item in services.items():
            print(f'{key:12} {probe(item)["state"]:10} {item["url"]}', flush=True)
        print(f'DevPulse     {devpulse_status(url, port):10} {url}', flush=True)
        return 0
    # Preflight before starting anything: no replacement of old or unknown listeners.
    for key, item in services.items():
        current = probe(item)
        if current['state'] not in ('online', 'offline'):
            raise RuntimeError(f'{key}: {current["state"]} pada port {item["port"]}. Tutup proses pemilik secara manual.')
    if devpulse_status(url, port) == 'conflict':
        raise RuntimeError(f'Konflik port DevPulse {port}. Tidak menghentikan proses pemilik.')
    if devpulse_status(url, port) == 'offline':
        check_node()
    if service_manager.main(['start', 'all', '--no-browser']) != 0:
        return 1
    start_devpulse(url, port)
    print('\n[SIAP] Keempat web berjalan. Menutup browser tidak menghentikan server.', flush=True)
    print('DevPulse: Ctrl+C pada terminal DevPulse. Ecosystem: KELOLA-EKOSISTEM.bat > Stop.', flush=True)
    if not args.no_browser:
        for address in [item['url'] for item in services.values()] + [url]:
            webbrowser.open_new_tab(address)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f'[ERROR] {exc}', file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(130)
