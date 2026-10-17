from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from .config import load_config

QUANT_RE = re.compile(r"(UD-IQ\d[^._-]*|UD-Q\d[^._-]*|IQ\d[^._-]*|Q\d(?:_[A-Z0-9]+)+|F16|BF16|Q8_0)", re.I)


def infer_model_name(path: Path) -> str:
    name = path.stem
    # Strip common quant suffix while preserving useful family text.
    m = QUANT_RE.search(name)
    if m and m.start() > 3:
        base = name[:m.start()].rstrip("-_. ")
        return base or name
    return name


def infer_quant(path: Path) -> str | None:
    m = QUANT_RE.search(path.stem)
    return m.group(1) if m else None


def scan_models() -> list[dict[str, Any]]:
    cfg = load_config()
    roots = cfg.get("models", {}).get("scan_paths", [])
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for root in roots:
        p = Path(os.path.expandvars(str(root)))
        if not p.exists():
            continue
        try:
            for f in p.rglob("*.gguf"):
                try:
                    key = str(f.resolve()).lower()
                except Exception:
                    key = str(f).lower()
                if key in seen:
                    continue
                seen.add(key)
                try:
                    stat = f.stat()
                except Exception:
                    continue
                # MTP sidecars are still visible but clearly marked.
                lower = f.name.lower()
                role = "mtp-sidecar" if ("mtp" in lower and stat.st_size < 4 * 1024**3) else "model"
                out.append({
                    "path": str(f),
                    "filename": f.name,
                    "name": infer_model_name(f),
                    "quant": infer_quant(f),
                    "size_gb": stat.st_size / (1024 ** 3),
                    "mtime": stat.st_mtime,
                    "role": role,
                })
        except (PermissionError, OSError):
            continue
    out.sort(key=lambda x: (x["role"] != "model", -x["mtime"]))
    return out
