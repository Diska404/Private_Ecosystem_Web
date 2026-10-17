"""Long-term local telemetry storage with raw and aggregated retention tiers."""
from __future__ import annotations
import csv
import io
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

PERIODS = {'live':300, '1h':3600, '6h':21600,'24h':86400,'7d':604800,
           '30d':2592000,'90d':7776000,'180d':15552000,'365d':31536000}


def flatten_snapshot(s):
    out = {'cpu':s['cpu'].get('usage_percent'), 'cpu_temp':s['cpu'].get('temperature_c'),
           'cpu_power':s['cpu'].get('power_w'),'ram':s['memory'].get('percent'),
           'ram_bytes':s['memory'].get('used_bytes'), 'net_down':s['network'].get('down_bps'),
           'net_up':s['network'].get('up_bps'),'disk_read':s['disk_io'].get('read_bps'),
           'disk_write':s['disk_io'].get('write_bps')}
    for gpu in s['gpus']:
        key='gpu.'+gpu['id']+'.'
        for src,target in [('usage_percent','load'),('temperature_c','temp'),
                           ('memory_percent','vram'),('power_w','power')]:
            out[key+target] = gpu.get(src)
    return {k:v for k,v in out.items() if isinstance(v,(int,float)) and not isinstance(v,bool)}


class HistoryStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.lock = threading.Lock()
        self.last_cleanup = 0
        with self._connect() as conn:
            for name in ('raw','five_min','hourly'):
                conn.execute(f'CREATE TABLE IF NOT EXISTS {name} (ts INTEGER PRIMARY KEY, payload TEXT NOT NULL)')
            conn.execute('CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL)')

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(str(self.path),timeout=10)
        try:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA busy_timeout=8000')
            with conn:
                yield conn
        finally:
            conn.close()

    def record(self,snapshot):
        ts=int(snapshot['timestamp'])
        values=flatten_snapshot(snapshot)
        if not values: return
        with self.lock, self._connect() as conn:
            conn.execute('INSERT OR REPLACE INTO raw (ts,payload) VALUES (?,?)',
                         (ts,json.dumps(values,separators=(',',':'))))
            for table,width in [('five_min',300),('hourly',3600)]:
                key=ts//width*width
                old=conn.execute(f'SELECT payload FROM {table} WHERE ts=?',(key,)).fetchone()
                data=json.loads(old[0]) if old else {}
                for metric,value in values.items():
                    accumulator=data.setdefault(metric,[0,0])
                    accumulator[0] += value
                    accumulator[1] += 1
                conn.execute(f'INSERT OR REPLACE INTO {table} (ts,payload) VALUES (?,?)',
                             (key,json.dumps(data,separators=(',',':'))))
            if ts-self.last_cleanup >= 3600:
                conn.execute('DELETE FROM raw WHERE ts < ?',(ts-172800,))
                conn.execute('DELETE FROM five_min WHERE ts < ?',(ts-7776000,))
                conn.execute('DELETE FROM hourly WHERE ts < ?',(ts-31536000,))
                self.last_cleanup=ts

    def get_history(self,period='live',limit=260):
        if period not in PERIODS: period='live'
        table='raw' if PERIODS[period]<=86400 else ('five_min' if PERIODS[period]<=7776000 else 'hourly')
        since=int(time.time())-PERIODS[period]
        with self.lock, self._connect() as conn:
            rows=conn.execute(f'SELECT ts,payload FROM {table} WHERE ts>=? ORDER BY ts',(since,)).fetchall()
        points=[]
        for ts,payload in rows:
            data=json.loads(payload)
            if table != 'raw':
                data={key:round(total/count,4) for key,(total,count) in data.items() if count}
            points.append({'ts':ts,**data})
        if len(points)>limit:
            # mean-per-bin resampling preserves spikes better than dropping alternate records.
            binned=[]
            for i in range(limit):
                window=points[i*len(points)//limit:(i+1)*len(points)//limit]
                if not window: continue
                acc={}
                for point in window:
                    for k,v in point.items():
                        if k=='ts': continue
                        acc.setdefault(k,[]).append(v)
                binned.append({'ts':window[-1]['ts'],**{k:round(sum(v)/len(v),4) for k,v in acc.items()}})
            points=binned
        return {'period':period,'points':points,'source':table,'count':len(points)}

    def export_csv(self,period='24h'):
        data=self.get_history(period,limit=200000)
        points=data['points']
        columns=['ts']+sorted({k for point in points for k in point if k!='ts'})
        out=io.StringIO()
        writer=csv.DictWriter(out,fieldnames=columns,extrasaction='ignore')
        writer.writeheader()
        writer.writerows(points)
        return out.getvalue()
