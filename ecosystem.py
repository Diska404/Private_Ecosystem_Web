"""Shared loopback service registry and ownership protocol; standard library only."""
from __future__ import annotations
import hashlib
import hmac
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import socket
import urllib.request

ROOT = Path(__file__).resolve().parent
VERSION = '2.1.0'
PROTOCOL = 'local-work-v2.1'
WORKSPACE = hashlib.sha256(str(ROOT).lower().encode()).hexdigest()[:20]
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
KINDS = {'hub': 'local-work-hub', 'ai': 'local-ai-control-center', 'signaldeck': 'signaldeck'}
ENV_PORTS = {'hub': ('ECOSYSTEM_PORT',), 'ai': ('ECOSYSTEM_AI_PORT',),
             'signaldeck': ('ECOSYSTEM_SIGNALDECK_PORT', 'SIGNALDECK_PORT')}


def registry():
    path = Path(os.environ.get('ECOSYSTEM_CONFIG', ROOT / 'ecosystem.json'))
    config = json.loads(path.read_text(encoding='utf-8-sig'))
    result = {}
    for key, kind in KINDS.items():
        row = config['services'][key]
        raw = next((os.environ[e] for e in ENV_PORTS[key] if e in os.environ), row['port'])
        if isinstance(raw, bool) or str(raw) != str(int(raw)):
            raise ValueError(f'Port {key} harus bilangan bulat')
        port = int(raw)
        if not 1024 <= port <= 65535:
            raise ValueError(f'Port {key} harus antara 1024 dan 65535')
        result[key] = {'name': str(row['name']), 'port': port, 'service': kind,
                       'url': f'http://127.0.0.1:{port}/'}
    if len({r['port'] for r in result.values()}) != len(result):
        raise ValueError('Port ketiga layanan harus berbeda')
    return result


def identity(key):
    return {'service': KINDS[key], 'version': VERSION, 'ecosystem': PROTOCOL,
            'workspace': WORKSPACE, 'instance': os.environ.get('ECOSYSTEM_INSTANCE', ''),
            'pid': os.getpid(), 'managed': bool(os.environ.get('ECOSYSTEM_CONTROL_TOKEN'))}


def occupied(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=.25):
            return True
    except OSError:
        return False


def probe(item):
    info = None
    try:
        with OPENER.open(item['url'] + 'api/health', timeout=.9) as response:
            info = json.loads(response.read(16384))
        if not isinstance(info, dict):
            info = None
    except (OSError, ValueError, TypeError):
        pass
    recognized = bool(info and info.get('service') == item['service'])
    compatible = bool(recognized and info.get('ecosystem') == PROTOCOL
                      and info.get('version') == VERSION and info.get('workspace') == WORKSPACE)
    busy = info is not None or occupied(item['port'])
    state = 'online' if compatible else ('outdated' if recognized else ('conflict' if busy else 'offline'))
    return {**item, 'online': recognized, 'compatible': compatible, 'state': state,
            'ready': bool(compatible and info.get('ok') is True),
            'version': info.get('version', 'unknown') if info else None,
            'demo': bool(info and info.get('demo')), 'health': info if recognized else None}


def apps_status():
    items = registry()
    with ThreadPoolExecutor(max_workers=len(items)) as pool:
        states = list(pool.map(probe, items.values()))
    return {'version': VERSION, 'ecosystem': PROTOCOL, 'apps': dict(zip(items, states))}


def authorized_shutdown(headers):
    token = os.environ.get('ECOSYSTEM_CONTROL_TOKEN', '')
    return bool(token and not headers.get('Origin') and hmac.compare_digest(
        headers.get('X-Ecosystem-Token', ''), token))
