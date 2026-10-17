"""Optional LibreHardwareMonitor integration. No simulated measurements."""
from __future__ import annotations
import json
import math
import re
import time
import urllib.request


class LibreHardwareBridge:
    def __init__(self):
        self.last_poll = 0.0
        self.cache = []
        self.source = 'offline'
        self.note = 'Jalankan LibreHardwareMonitor dan aktifkan Remote Web Server (port 8085), atau WMI.'
        self._wmi_retry = 0.0

    def read(self):
        if time.monotonic() - self.last_poll < 4:
            return self.cache
        self.last_poll = time.monotonic()
        try:
            with urllib.request.urlopen('http://127.0.0.1:8085/data.json', timeout=0.8) as response:
                body = response.read(3_000_000)
            data = json.loads(body)
            results = []
            self._walk(data, [], results)
            if results:
                self.cache = results
                self.source = 'http'
                self.note = 'Terhubung melalui LibreHardwareMonitor Remote Web Server.'
                return self.cache
        except Exception:
            pass
        try:
            # pythoncom initialization must occur inside the collector thread.
            import pythoncom
            import wmi
            pythoncom.CoInitialize()
            try:
                connection = wmi.WMI(namespace=r'root\LibreHardwareMonitor')
                hardware = {str(h.Identifier): str(h.Name) for h in connection.Hardware()}
                results = []
                for s in connection.Sensor():
                    try:
                        value = float(s.Value)
                        if not math.isfinite(value):
                            continue
                    except (TypeError, ValueError, OverflowError):
                        continue
                    kind = str(s.SensorType)
                    unit = {'Temperature':'°C', 'Load':'%', 'Power':'W', 'Clock':'MHz',
                            'Fan':'RPM', 'Voltage':'V', 'Current':'A', 'Data':'GB',
                            'SmallData':'MB', 'Throughput':'B/s', 'Control':'%'}.get(kind, '')
                    parent = str(s.Parent)
                    device = hardware.get(parent, parent.strip('/').split('/')[-1] or 'Hardware')
                    results.append({'device':device, 'metric':str(s.Name), 'type':kind,
                                    'value':round(value,2), 'unit':unit, 'source':'LHM WMI', 'parent':parent})
            finally:
                pythoncom.CoUninitialize()
            if results:
                self.cache = results
                self.source = 'wmi'
                self.note = 'Terhubung melalui LibreHardwareMonitor WMI.'
                return self.cache
        except Exception:
            pass
        self.cache = []
        self.source = 'offline'
        self.note = 'Sensor suhu CPU/kipas/daya membutuhkan LibreHardwareMonitor (WMI/Remote Web Server).'
        return []

    def _walk(self, node, parents, output):
        if isinstance(node, list):
            for child in node:
                self._walk(child, parents, output)
            return
        if not isinstance(node, dict):
            return
        title = str(node.get('Text', '')).strip()
        children = node.get('Children', [])
        image = str(node.get('ImageURL', '')).lower()
        raw_value = node.get('Value')
        if raw_value not in (None, '', '-'):
            parsed = parse_value(str(raw_value))
            if parsed:
                value, unit = parsed
                type_name = {'°C':'Temperature','%':'Load','W':'Power',
                             'RPM':'Fan','MHz':'Clock','GHz':'Clock','V':'Voltage',
                             'A':'Current','GB':'Data','MB':'SmallData'}.get(unit,'Other')
                if unit == 'GHz':
                    value *= 1000
                    unit = 'MHz'
                device = next((p for p in reversed(parents) if any(x in p.lower() for x in ('cpu','intel','nvidia','amd','gpu','memory','ssd','hdd','disk','battery'))), parents[-1] if parents else 'Hardware')
                output.append({'device':device, 'metric':title, 'type':type_name,
                               'value':round(value,2), 'unit':unit, 'source':'LHM HTTP', 'parent':'/'.join(parents)})
        new_parents = parents + ([title] if title else [])
        self._walk(children, new_parents, output)


def parse_value(raw):
    # Common LHM values: '54.0 °C', '1,520 RPM', '2.45 GHz', '16.3 %'.
    match = re.match(r'^\s*([-+]?\d[\d.,]*)\s*(°C|%|W|RPM|MHz|GHz|V|A|GB|MB)\s*$', raw)
    if not match:
        return None
    numeric, unit = match.groups()
    if ',' in numeric and '.' in numeric:
        numeric = numeric.replace(',', '')
    elif ',' in numeric:
        left, right = numeric.rsplit(',', 1)
        numeric = numeric.replace(',', '') if len(right) == 3 else numeric.replace(',', '.')
    try:
        value = float(numeric)
        return (value, unit) if math.isfinite(value) else None
    except ValueError:
        return None
