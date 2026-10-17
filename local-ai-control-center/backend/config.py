from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
from ecosystem import registry
CONFIG_DIR = ROOT / "config"
CONFIG_FILE = CONFIG_DIR / "app.json"
DATA_DIR = Path(os.environ.get("LOCAL_AI_DATA_DIR", ROOT / "data"))
LOG_DIR = ROOT / "logs"

DEFAULT_CONFIG: dict[str, Any] = {
    "app": {
        "host": "127.0.0.1",
        "port": 8765,
        "gateway_port": 8766,
        "open_browser": True,
        "telemetry_interval_ms": 500,
    },
    "runtime": {
        "llama_server_path": "",
        "host": "127.0.0.1",
        "port": 8080,
        "model_path": "",
        "context_size": 65536,
        "gpu_layers": "auto",
        "main_gpu": 0,
        "tensor_split": "",
        "cache_type_k": "q8_0",
        "cache_type_v": "q8_0",
        "flash_attention": True,
        "mtp": False,
        "batch_size": 2048,
        "ubatch_size": 512,
        "parallel": 1,
        "fit": True,
        "fit_target_mib": 1536,
        "extra_args": "",
    },
    "models": {
        "scan_paths": [
            r"Y:\GFL2_AI\models",
            r"Y:\GFL2_AI\models\hf-cache",
            r"C:\AI\models",
            r"D:\AI\models",
        ]
    },
    "clients": {
        "hermes_log": r"%LOCALAPPDATA%\hermes\logs\llama-server.log",
        "hermes_names": ["hermes", "hermes-agent"],
        "openclaw_names": ["openclaw", "open-claw"],
    },
    "agent": {
        "permission_profile": "safe",
        "max_steps": 8,
        "tool_timeout_seconds": 30,
    },
    "charts": {
        "preset": "telemetry-mix",
        "dashboard": {
            "generation": "wave",
            "context": "gauge",
            "gpu0": "wave",
            "gpu1": "donut",
            "ram": "bar"
        },
        "usage": {
            "tokens": "wave",
            "models": "bar",
            "clients": "donut",
            "runtime": "timeline",
            "activity": "heatmap"
        }
    },
}


def _deep_merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in incoming.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any]:
    ensure_dirs()
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
    try:
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
        if not isinstance(raw,dict): raise ValueError('Konfigurasi harus berupa objek JSON')
    except (OSError,ValueError) as exc:
        raise ValueError('config/app.json tidak dapat dibaca; perbaiki atau pulihkan backup sebelum melanjutkan') from exc
    result = _deep_merge(DEFAULT_CONFIG, raw)
    services = registry()
    result['app'].update(host='127.0.0.1',port=services['ai']['port'],signaldeck_port=services['signaldeck']['port'])
    return result


def save_config(config: dict[str, Any]) -> None:
    ensure_dirs()
    CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def resolve_llama_server(config: dict[str, Any]) -> str | None:
    candidate = str(config.get("runtime", {}).get("llama_server_path", "")).strip()
    if candidate:
        expanded = os.path.expandvars(candidate)
        if Path(expanded).exists():
            return expanded
    for name in ("llama-server.exe", "llama-server"):
        found = shutil.which(name)
        if found:
            return found
    return None


def expand_path(value: str) -> str:
    return os.path.expandvars(os.path.expanduser(value))
