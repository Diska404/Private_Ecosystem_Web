"""Read actual machine telemetry, with opt-in/clearly-labelled demonstration mode."""
from __future__ import annotations
import math
import os
import platform
import re
import socket
import subprocess
import time
from datetime import datetime, timezone

import psutil
from librehardware import LibreHardwareBridge


def finite(value, digits=1):
    try:
        x = float(value)
        return round(x, digits) if math.isfinite(x) else None
    except (ValueError, TypeError, OverflowError):
        return None


def gpu_name_matches(a, b):
    def normalize(s):
        return re.sub(r'\b(nvidia|intel|graphics|laptop|gpu|geforce|adapter|\(r\)|\(tm\))\b', '', s.lower()).replace(' ', '')
    na, nb = normalize(a), normalize(b)
    return bool(na and nb and (na in nb or nb in na))


def windows_adapters():
    if os.name != 'nt':
        return []
    command = ('Get-CimInstance Win32_VideoController | '
               'Select-Object Name,AdapterRAM,PNPDeviceID | ConvertTo-Json -Compress')
    try:
        r = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],
                           capture_output=True, text=True, timeout=7, creationflags=0x08000000)
        import json
        data = json.loads(r.stdout)
        if isinstance(data, dict):
            data = [data]
        return [str(x.get('Name','')).strip() for x in data if x.get('Name') and 'Microsoft Basic' not in str(x.get('Name'))]
    except Exception:
        return []


class NVMLProvider:
    def __init__(self):
        self.nvml = None
        self.status = 'Tidak tersedia (NVIDIA driver/NVML tidak ditemukan)'
        try:
            import pynvml
            pynvml.nvmlInit()
            self.nvml = pynvml
            self.status = 'Aktif'
        except Exception as exc:
            self.status = f'NVML tidak tersedia: {type(exc).__name__}'

    def read(self):
        if self.nvml is None:
            return []
        n = self.nvml
        try:
            count = n.nvmlDeviceGetCount()
        except Exception:
            return []
        results = []
        for i in range(count):
            try:
                device = n.nvmlDeviceGetHandleByIndex(i)
                name = n.nvmlDeviceGetName(device)
                if isinstance(name, bytes):
                    name = name.decode('utf-8','replace')
                gpu = {'id':f'nvidia-{i}', 'name':name, 'vendor':'NVIDIA',
                       'usage_percent':None, 'temperature_c':None,
                       'memory_total_bytes':None,'memory_used_bytes':None,'memory_percent':None,
                       'power_w':None,'power_limit_w':None,'fan_percent':None,
                       'clock_mhz':None,'memory_clock_mhz':None,
                       'encoder_percent':None,'decoder_percent':None,
                       'source':'NVIDIA NVML'}
                def get(fn, *args):
                    try: return fn(device, *args)
                    except Exception: return None
                uuid = get(n.nvmlDeviceGetUUID) if hasattr(n,'nvmlDeviceGetUUID') else None
                if isinstance(uuid,bytes): uuid=uuid.decode('utf-8','replace')
                # Keep historical metric IDs intact; profiles use the device UUID when available.
                gpu['stable_id'] = str(uuid) if uuid else None
                util = get(n.nvmlDeviceGetUtilizationRates)
                if util is not None:
                    gpu['usage_percent'] = finite(util.gpu)
                memory = get(n.nvmlDeviceGetMemoryInfo)
                if memory:
                    gpu['memory_total_bytes'] = int(memory.total)
                    gpu['memory_used_bytes'] = int(memory.used)
                    gpu['memory_percent'] = finite(100*memory.used/max(memory.total,1))
                gpu['temperature_c'] = finite(get(n.nvmlDeviceGetTemperature, n.NVML_TEMPERATURE_GPU))
                power = get(n.nvmlDeviceGetPowerUsage)
                gpu['power_w'] = finite(power/1000) if power is not None else None
                limit = get(n.nvmlDeviceGetEnforcedPowerLimit)
                if limit is None: limit = get(n.nvmlDeviceGetPowerManagementLimit)
                gpu['power_limit_w'] = finite(limit/1000) if limit is not None else None
                gpu['fan_percent'] = finite(get(n.nvmlDeviceGetFanSpeed))
                gpu['clock_mhz'] = finite(get(n.nvmlDeviceGetClockInfo,n.NVML_CLOCK_GRAPHICS),0)
                gpu['memory_clock_mhz'] = finite(get(n.nvmlDeviceGetClockInfo,n.NVML_CLOCK_MEM),0)
                for key, method in [('encoder_percent','nvmlDeviceGetEncoderUtilization'),('decoder_percent','nvmlDeviceGetDecoderUtilization')]:
                    value = get(getattr(n,method)) if hasattr(n,method) else None
                    if isinstance(value, tuple): gpu[key] = finite(value[0])
                results.append(gpu)
            except Exception:
                continue
        return results


class HardwareCollector:
    def __init__(self, demo=False):
        self.demo = demo
        self.started = time.time()
        self.nvml = NVMLProvider() if not demo else None
        self.lhm = LibreHardwareBridge() if not demo else None
        self.adapter_names = windows_adapters() if not demo else []
        self.cpu_name = self._cpu_name()
        self._last_net = None
        self._last_disk = None
        self._last_time = None
        psutil.cpu_percent(interval=None, percpu=True)
        self.counter = 0

    def _cpu_name(self):
        if self.demo: return 'Intel Core i7-13700HX (simulasi)'
        if os.name == 'nt':
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
                    return winreg.QueryValueEx(key,'ProcessorNameString')[0].strip()
            except Exception: pass
        try:
            with open('/proc/cpuinfo',encoding='utf8') as file:
                match = re.search(r'^model name\s*:\s*(.+)$',file.read(),re.M)
                if match: return match.group(1)
        except Exception: pass
        return platform.processor() or 'CPU'

    def collect(self):
        if self.demo:
            return self._demo()
        timestamp = time.time()
        cores = psutil.cpu_percent(interval=None,percpu=True)
        usage = finite(sum(cores)/len(cores)) if cores else finite(psutil.cpu_percent(interval=None))
        freq = psutil.cpu_freq()
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        cpu = {'name':self.cpu_name, 'usage_percent':usage,
               'per_core_percent':[finite(x) for x in cores],
               'physical_cores':psutil.cpu_count(logical=False),'threads':psutil.cpu_count(),
               'frequency_mhz':finite(freq.current,0) if freq else None,
               'frequency_max_mhz':finite(freq.max,0) if freq and freq.max else None,
               'temperature_c':None,'power_w':None,'fan_rpm':None}
        memory = {'total_bytes':mem.total, 'used_bytes':mem.used,
                  'available_bytes':mem.available,'percent':finite(mem.percent),
                  'swap_total_bytes':swap.total,'swap_used_bytes':swap.used,
                  'swap_percent':finite(swap.percent)}
        gpus = self.nvml.read()
        for name in self.adapter_names:
            if any(gpu_name_matches(name,gpu['name']) for gpu in gpus):
                continue
            vendor = 'NVIDIA' if 'nvidia' in name.lower() else ('Intel' if 'intel' in name.lower() else ('AMD' if 'amd' in name.lower() or 'radeon' in name.lower() else 'Lainnya'))
            gpus.append({'id':'adapter-'+str(len(gpus)), 'name':name, 'vendor':vendor,
                         'usage_percent':None,'temperature_c':None,
                         'memory_total_bytes':None,'memory_used_bytes':None,'memory_percent':None,
                         'power_w':None,'power_limit_w':None,'fan_percent':None,
                         'clock_mhz':None,'memory_clock_mhz':None,'encoder_percent':None,'decoder_percent':None,
                         'source':'Windows Adapter (sensor tambahan: LHM)'})
        lhm_sensors = self.lhm.read()
        self._merge_lhm(cpu,gpus,lhm_sensors)
        disk_counters = psutil.disk_io_counters()
        net_counters = psutil.net_io_counters()
        interval = max(timestamp-self._last_time,0.01) if self._last_time else None
        disk_io = {'read_bps':None,'write_bps':None,'read_bytes':0,'write_bytes':0}
        if disk_counters:
            disk_io['read_bytes'] = disk_counters.read_bytes
            disk_io['write_bytes'] = disk_counters.write_bytes
            if self._last_disk and interval:
                disk_io['read_bps'] = max(0,(disk_counters.read_bytes-self._last_disk.read_bytes)/interval)
                disk_io['write_bps'] = max(0,(disk_counters.write_bytes-self._last_disk.write_bytes)/interval)
        network = {'down_bps':None,'up_bps':None,'bytes_recv':net_counters.bytes_recv,'bytes_sent':net_counters.bytes_sent}
        if self._last_net and interval:
            network['down_bps'] = max(0,(net_counters.bytes_recv-self._last_net.bytes_recv)/interval)
            network['up_bps'] = max(0,(net_counters.bytes_sent-self._last_net.bytes_sent)/interval)
        self._last_time = timestamp
        self._last_net = net_counters
        self._last_disk = disk_counters
        storage = []
        seen = set()
        for part in psutil.disk_partitions(all=False):
            key = part.mountpoint.lower()
            if key in seen: continue
            seen.add(key)
            try:
                du = psutil.disk_usage(part.mountpoint)
                storage.append({'device':part.device,'mount':part.mountpoint,
                                'fstype':part.fstype, 'total_bytes':du.total,
                                'used_bytes':du.used,'free_bytes':du.free,'percent':finite(du.percent)})
            except (OSError,PermissionError): pass
        battery = None
        try:
            b = psutil.sensors_battery()
            if b: battery = {'percent':finite(b.percent),'plugged':b.power_plugged,'secsleft':b.secsleft}
        except Exception: pass
        sensors = self._build_sensors(cpu,memory,gpus,lhm_sensors)
        return {'timestamp':timestamp,'demo':False,
                'system':{'hostname':socket.gethostname(),'os':platform.platform(),
                          'uptime_seconds':int(timestamp-psutil.boot_time()), 'battery':battery},
                'cpu':cpu, 'memory':memory,'gpus':gpus,'storage':storage,
                'disk_io':disk_io,'network':network,'sensors':sensors,
                'sources':{'system':'psutil','nvidia':self.nvml.status,
                           'lhm':self.lhm.source,'lhm_note':self.lhm.note}}

    @staticmethod
    def _merge_lhm(cpu,gpus,sensors):
        for s in sensors:
            device = str(s['device']).lower()
            metric = str(s['metric']).lower()
            typ = s['type']
            value = s['value']
            is_cpu = ('cpu' in device or 'processor' in device) and not any(x in device for x in ('gpu','nvidia','radeon'))
            if is_cpu:
                if typ=='Temperature' and any(x in metric for x in ('package','tctl','tdie','cpu core')):
                    if cpu['temperature_c'] is None or 'package' in metric: cpu['temperature_c'] = value
                if typ=='Power' and ('package' in metric or 'cpu' in metric): cpu['power_w'] = value
                if typ=='Fan' and cpu['fan_rpm'] is None: cpu['fan_rpm'] = value
            for gpu in gpus:
                if gpu_name_matches(device,gpu['name']) or (gpu['vendor'].lower() in device and any(x in device for x in ('gpu','graphics')) and sum(g['vendor']==gpu['vendor'] for g in gpus)==1):
                    mappings = [('Temperature','temperature_c',('core','gpu','package')),
                                ('Load','usage_percent',('core','gpu core')),
                                ('Power','power_w',('package','total','gpu')),
                                ('Fan','fan_percent',('fan',)),
                                ('Clock','clock_mhz',('core','gpu'))]
                    for t, key, words in mappings:
                        if typ==t and any(x in metric for x in words) and gpu.get(key) is None:
                            if typ != 'Fan' or s['unit']=='%': gpu[key] = value
                    if typ=='Load' and 'memory' in metric and gpu['memory_percent'] is None: gpu['memory_percent'] = value
                    if gpu['source']!='NVIDIA NVML': gpu['source']='LibreHardwareMonitor'

    @staticmethod
    def _build_sensors(cpu,memory,gpus,extra):
        data = []
        def add(device,metric,value,unit,source,typ):
            if value is not None:
                data.append({'device':device,'metric':metric,'value':value,'unit':unit,'source':source,'type':typ})
        add('CPU','Total Load',cpu['usage_percent'],'%','psutil','Load')
        add('CPU','CPU Frequency',cpu['frequency_mhz'],'MHz','psutil','Clock')
        for i,val in enumerate(cpu['per_core_percent']): add('CPU',f'Logical Core {i}',val,'%','psutil','Load')
        add('RAM','Memory Load',memory['percent'],'%','psutil','Load')
        for gpu in gpus:
            for key,metric,unit,typ in [('usage_percent','GPU Core Load','%','Load'),('temperature_c','GPU Temperature','°C','Temperature'),
                                        ('memory_percent','VRAM Load','%','Load'),('power_w','GPU Board Power','W','Power'),
                                        ('fan_percent','Fan Duty','%','Control'),('clock_mhz','GPU Clock','MHz','Clock'),
                                        ('encoder_percent','Encoder Utilization','%','Load'),('decoder_percent','Decoder Utilization','%','Load')]:
                add(gpu['name'],metric,gpu.get(key),unit,gpu['source'],typ)
        data.extend(extra)
        return data

    def _demo(self):
        """Explicit demo mode for trying the interface without Windows hardware."""
        import math
        t = time.time()
        self.counter += 1
        phase = self.counter/7
        wave = lambda bias,mag,speed: max(0,min(100,bias+mag*math.sin(phase*speed)))
        cpu_load = round(wave(37,21,0.7),1)
        cpu={'name':self.cpu_name,'usage_percent':cpu_load,
             'per_core_percent':[round(wave(24+i%6*7,19,0.5+i/8),1) for i in range(20)],
             'physical_cores':14,'threads':20,'frequency_mhz':round(3250+560*math.sin(phase),0),
             'frequency_max_mhz':5000,'temperature_c':round(61+8*math.sin(phase/2),1),
             'power_w':round(65+24*math.sin(phase/2),1),'fan_rpm':round(2600+490*math.sin(phase),0)}
        mem={'total_bytes':64*2**30,'used_bytes':int((23+1.6*math.sin(phase/3))*2**30),
             'available_bytes':int((41-1.6*math.sin(phase/3))*2**30),
             'percent':round((23+1.6*math.sin(phase/3))/64*100,1),
             'swap_total_bytes':16*2**30,'swap_used_bytes':int(1.2*2**30),'swap_percent':7.5}
        gpus=[]
        for idx,name,vr,power,base in [(0,'NVIDIA GeForce RTX 4050 Laptop GPU',6,115,23),
                                        (1,'NVIDIA GeForce RTX 5070',12,250,61)]:
            usage=round(wave(base,18,0.8+idx*0.21),1)
            used=int((vr*(0.25+usage/175))*2**30)
            gpus.append({'id':f'nvidia-{idx}','name':name,'vendor':'NVIDIA','usage_percent':usage,
                         'temperature_c':round(51+idx*13+6*math.sin(phase/2),1),
                         'memory_total_bytes':vr*2**30,'memory_used_bytes':used,
                         'memory_percent':round(100*used/(vr*2**30),1),'power_w':round((40+usage*power/140),1),
                         'power_limit_w':power,'fan_percent':round(28+usage/2,1),
                         'clock_mhz':2400,'memory_clock_mhz':10500,'encoder_percent':12.5,
                         'decoder_percent':2.1,'source':'SIMULASI'})
        gpus.append({'id':'adapter-2','name':'Intel UHD Graphics','vendor':'Intel',
                     'usage_percent':round(wave(12,8,0.9),1),'temperature_c':53.0,
                     'memory_total_bytes':None,'memory_used_bytes':None,'memory_percent':None,
                     'power_w':None,'power_limit_w':None,'fan_percent':None,'clock_mhz':900,
                     'memory_clock_mhz':None,'encoder_percent':None,'decoder_percent':None,'source':'SIMULASI'})
        net={'down_bps':(3+wave(27,24,0.9))*2**20/8,'up_bps':(1+wave(13,10,0.4))*2**20/8,
             'bytes_recv':int(1234*2**30),'bytes_sent':int(412*2**30)}
        disk={'read_bps':(15+wave(20,15,1.4))*2**20,'write_bps':(4+wave(9,7,0.8))*2**20,
              'read_bytes':int(280*2**30),'write_bytes':int(140*2**30)}
        disks=[{'device':x,'mount':x,'fstype':'NTFS','total_bytes':size*2**30,
                'used_bytes':int(size*used*2**30),'free_bytes':int(size*(1-used)*2**30),'percent':round(100*used,1)}
               for x,size,used in [('C:\\',953,.65),('D:\\',1863,.42)]]
        extra=[{'device':'CPU','metric':'CPU Package','value':cpu['temperature_c'],'unit':'°C','source':'SIMULASI','type':'Temperature'},
               {'device':'CPU','metric':'CPU Package Power','value':cpu['power_w'],'unit':'W','source':'SIMULASI','type':'Power'},
               {'device':'Laptop','metric':'CPU Fan','value':cpu['fan_rpm'],'unit':'RPM','source':'SIMULASI','type':'Fan'},
               {'device':'Motherboard','metric':'CPU Core Voltage','value':1.14,'unit':'V','source':'SIMULASI','type':'Voltage'}]
        return {'timestamp':t,'demo':True,'system':{'hostname':'DEMO-PREDATOR','os':'Windows 11 (simulasi)',
                  'uptime_seconds':102502,'battery':{'percent':87,'plugged':True,'secsleft':-2}},
                'cpu':cpu,'memory':mem,'gpus':gpus,'storage':disks,
                'disk_io':disk,'network':net,'sensors':self._build_sensors(cpu,mem,gpus,extra),
                'sources':{'system':'SIMULASI','nvidia':'SIMULASI','lhm':'demo','lhm_note':'Mode demo: angka bukan sensor nyata.'}}
