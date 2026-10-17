from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

from .config import expand_path, load_config

try:
    from pynvml import (
        nvmlInit, nvmlShutdown, nvmlDeviceGetCount, nvmlDeviceGetHandleByIndex,
        nvmlDeviceGetName, nvmlDeviceGetUtilizationRates, nvmlDeviceGetMemoryInfo,
        nvmlDeviceGetTemperature, nvmlDeviceGetPowerUsage, nvmlDeviceGetClockInfo,
        NVML_TEMPERATURE_GPU, NVML_CLOCK_GRAPHICS,
    )
    NVML_AVAILABLE = True
except Exception:
    NVML_AVAILABLE = False


class TelemetryState:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.gateway_last_seen: dict[str, float] = {}
        self.gateway_active: dict[str, int] = {"hermes": 0, "openclaw": 0, "web-chat": 0, "web-agent": 0}
        self.last_inference: dict[str, Any] = {}
        self.gen_history: deque[dict[str, Any]] = deque(maxlen=1200)
        self.context_by_client: dict[str, dict[str, Any]] = {}

    def mark_client(self, client: str, active_delta: int = 0) -> None:
        with self.lock:
            self.gateway_last_seen[client] = time.time()
            if active_delta:
                self.gateway_active[client] = max(0, self.gateway_active.get(client, 0) + active_delta)

    def set_context(self, client: str, used: int | None, capacity: int | None, source: str = "runtime") -> None:
        if used is None:
            return
        with self.lock:
            self.context_by_client[client] = {
                "used": int(used),
                "capacity": int(capacity or 0),
                "source": source,
                "updated_at": time.time(),
            }

    def push_tps(self, value: float | None, source: str = "log") -> None:
        if value is None:
            return
        with self.lock:
            self.gen_history.append({"ts": time.time(), "value": float(value), "source": source})


STATE = TelemetryState()


class LlamaLogParser:
    TG_RE = re.compile(r"n_gen\s*=\s*(\d+).*?tg\s*=\s*([\d.]+)\s*t/s.*?tg_3s\s*=\s*([\d.]+)\s*t/s", re.I)
    PROMPT_RE = re.compile(r"prompt eval time\s*=.*?/\s*(\d+)\s+tokens.*?([\d.]+)\s+tokens per second", re.I)
    EVAL_RE = re.compile(r"(?<!prompt )eval time\s*=.*?/\s*(\d+)\s+tokens.*?([\d.]+)\s+tokens per second", re.I)

    def __init__(self) -> None:
        self.last_read_signature: tuple[str, float, int] | None = None
        self.last: dict[str, Any] = {
            "state": "idle", "generation_tps": None, "prompt_tps": None,
            "generated_tokens": None, "prompt_tokens": None, "source": None,
        }

    def candidate_logs(self) -> list[Path]:
        cfg = load_config()
        paths = [Path(__file__).resolve().parents[1] / "logs" / "llama-server.log"]
        hermes = cfg.get("clients", {}).get("hermes_log")
        if hermes:
            paths.append(Path(expand_path(hermes)))
        return [p for p in paths if p.exists()]

    def parse(self) -> dict[str, Any]:
        candidates = self.candidate_logs()
        if not candidates:
            return dict(self.last)
        path = max(candidates, key=lambda p: p.stat().st_mtime)
        try:
            with path.open("rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - 120_000), os.SEEK_SET)
                text = f.read().decode("utf-8", errors="ignore")
        except Exception:
            return dict(self.last)

        lines = text.splitlines()
        state = "idle"
        last_start = -1
        last_prompt_done = -1
        last_end = -1
        gen_tps = None
        prompt_tps = None
        generated = None
        prompt_tokens = None
        live_idx = -1

        for i, line in enumerate(lines):
            lower = line.lower()
            if "processing task" in lower or "launch_slot_with_task" in lower:
                last_start = i
            if "prompt done" in lower:
                last_prompt_done = i
            if "stop processing" in lower or "all slots are idle" in lower:
                last_end = i
            m = self.TG_RE.search(line)
            if m:
                generated = int(m.group(1))
                gen_tps = float(m.group(3))
                live_idx = i
            m = self.PROMPT_RE.search(line)
            if m:
                prompt_tokens = int(m.group(1))
                prompt_tps = float(m.group(2))
            m = self.EVAL_RE.search(line)
            if m:
                generated = int(m.group(1))
                gen_tps = float(m.group(2))

        if last_start > last_end:
            state = "generating" if last_prompt_done > last_start else "prompt"
        if live_idx < last_start and state != "idle":
            # Avoid reusing a stale live sample from the previous request.
            pass

        self.last = {
            "state": state,
            "generation_tps": gen_tps,
            "prompt_tps": prompt_tps,
            "generated_tokens": generated,
            "prompt_tokens": prompt_tokens,
            "source": str(path),
            "updated_at": path.stat().st_mtime,
        }
        if gen_tps:
            STATE.push_tps(gen_tps, "llama-log")
        return dict(self.last)


LOG_PARSER = LlamaLogParser()


def _gpu_nvml() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    nvmlInit()
    try:
        for idx in range(nvmlDeviceGetCount()):
            h = nvmlDeviceGetHandleByIndex(idx)
            name = nvmlDeviceGetName(h)
            if isinstance(name, bytes):
                name = name.decode(errors="ignore")
            util = nvmlDeviceGetUtilizationRates(h)
            mem = nvmlDeviceGetMemoryInfo(h)
            try:
                temp = nvmlDeviceGetTemperature(h, NVML_TEMPERATURE_GPU)
            except Exception:
                temp = None
            try:
                power = nvmlDeviceGetPowerUsage(h) / 1000.0
            except Exception:
                power = None
            try:
                clock = nvmlDeviceGetClockInfo(h, NVML_CLOCK_GRAPHICS)
            except Exception:
                clock = None
            out.append({
                "index": idx,
                "name": str(name).replace("NVIDIA GeForce ", "").replace(" Laptop GPU", ""),
                "utilization": float(util.gpu),
                "memory_used_gb": mem.used / (1024 ** 3),
                "memory_total_gb": mem.total / (1024 ** 3),
                "memory_percent": (mem.used / mem.total * 100.0) if mem.total else 0.0,
                "temperature_c": temp,
                "power_w": power,
                "clock_mhz": clock,
            })
    finally:
        try:
            nvmlShutdown()
        except Exception:
            pass
    return out


def _gpu_smi() -> list[dict[str, Any]]:
    query = "index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,clocks.current.graphics"
    try:
        p = subprocess.run(
            ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        if p.returncode != 0:
            return []
        out = []
        for line in p.stdout.splitlines():
            vals = [x.strip() for x in line.split(",")]
            if len(vals) < 8:
                continue
            used, total = float(vals[3]), float(vals[4])
            out.append({
                "index": int(vals[0]), "name": vals[1].replace("NVIDIA GeForce ", "").replace(" Laptop GPU", ""),
                "utilization": float(vals[2]), "memory_used_gb": used / 1024.0, "memory_total_gb": total / 1024.0,
                "memory_percent": used / total * 100.0 if total else 0.0,
                "temperature_c": None if vals[5] in {"N/A", "[N/A]"} else float(vals[5]),
                "power_w": None if vals[6] in {"N/A", "[N/A]"} else float(vals[6]),
                "clock_mhz": None if vals[7] in {"N/A", "[N/A]"} else float(vals[7]),
            })
        return out
    except Exception:
        return []


def get_gpus() -> list[dict[str, Any]]:
    if NVML_AVAILABLE:
        try:
            return _gpu_nvml()
        except Exception:
            pass
    return _gpu_smi()


def _process_info(proc: psutil.Process) -> dict[str, Any]:
    try:
        with proc.oneshot():
            return {
                "pid": proc.pid,
                "name": proc.name(),
                "cmdline": " ".join(proc.cmdline()),
                "cpu_percent": proc.cpu_percent(interval=None),
                "ram_gb": proc.memory_info().rss / (1024 ** 3),
                "create_time": proc.create_time(),
            }
    except Exception:
        return {"pid": proc.pid, "name": "unknown", "cmdline": "", "cpu_percent": 0, "ram_gb": 0, "create_time": 0}


def detect_processes() -> dict[str, Any]:
    cfg = load_config()
    hermes_names = [s.lower() for s in cfg.get("clients", {}).get("hermes_names", [])]
    openclaw_names = [s.lower() for s in cfg.get("clients", {}).get("openclaw_names", [])]
    result = {"hermes": [], "openclaw": [], "llama": []}
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (p.info.get("name") or "").lower()
            cmd = " ".join(p.info.get("cmdline") or []).lower()
            blob = f"{name} {cmd}"
            if "llama-server" in blob:
                result["llama"].append(_process_info(p))
            if any(x in blob for x in hermes_names if x):
                result["hermes"].append(_process_info(p))
            if any(x in blob for x in openclaw_names if x):
                result["openclaw"].append(_process_info(p))
        except Exception:
            continue
    return result


def get_system() -> dict[str, Any]:
    vm = psutil.virtual_memory()
    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "cpu_count": psutil.cpu_count(logical=True),
        "ram_used_gb": (vm.total - vm.available) / (1024 ** 3),
        "ram_total_gb": vm.total / (1024 ** 3),
        "ram_percent": vm.percent,
    }


def get_clients(processes: dict[str, Any] | None = None) -> dict[str, Any]:
    processes = processes or detect_processes()
    now = time.time()
    out: dict[str, Any] = {}
    with STATE.lock:
        for key in ("hermes", "openclaw", "web-chat", "web-agent"):
            running = bool(processes.get(key, [])) if key in ("hermes", "openclaw") else True
            last_seen = STATE.gateway_last_seen.get(key)
            connected = running or (last_seen is not None and now - last_seen < 60)
            active = STATE.gateway_active.get(key, 0) > 0
            out[key] = {
                "running": running,
                "connected": connected,
                "active": active,
                "last_seen": last_seen,
                "processes": processes.get(key, []),
                "context": STATE.context_by_client.get(key),
            }
    return out


def snapshot() -> dict[str, Any]:
    processes = detect_processes()
    llama = LOG_PARSER.parse()
    system = get_system()
    gpus = get_gpus()
    with STATE.lock:
        history = list(STATE.gen_history)[-120:]
    return {
        "ts": time.time(),
        "iso_time": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "system": system,
        "gpus": gpus,
        "processes": processes,
        "clients": get_clients(processes),
        "llama": llama,
        "tps_history": history,
    }
