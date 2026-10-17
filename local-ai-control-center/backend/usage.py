from __future__ import annotations

import asyncio
import json
import math
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psutil

from .config import load_config
from .database import db, now_iso
from .models import infer_quant

RANGE_DAYS: dict[str, int | None] = {
    "1d": 1,
    "1w": 7,
    "1m": 30,
    "3m": 90,
    "6m": 183,
    "1y": 365,
    "all": None,
}


def _local_now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def _iso_from_epoch(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_local_now().tzinfo)
        return dt
    except Exception:
        return None


def _period_start(period: str) -> datetime | None:
    days = RANGE_DAYS.get(period, 30)
    if days is None:
        return None
    return _local_now() - timedelta(days=days)


def _clip_seconds(start: datetime | None, end: datetime | None, period_start: datetime | None, now: datetime) -> float:
    if start is None:
        return 0.0
    actual_start = max(start, period_start) if period_start else start
    actual_end = min(end or now, now)
    if actual_end <= actual_start:
        return 0.0
    return (actual_end - actual_start).total_seconds()


def _parse_runtime_args(proc: psutil.Process) -> dict[str, Any]:
    try:
        args = proc.cmdline()
    except Exception:
        args = []
    model_path = None
    context = None
    for i, arg in enumerate(args):
        low = str(arg).lower()
        if low in {"-m", "--model"} and i + 1 < len(args):
            model_path = args[i + 1]
        elif low in {"-c", "--ctx-size", "--context-size"} and i + 1 < len(args):
            try:
                context = int(args[i + 1])
            except Exception:
                pass
    cfg = load_config().get("runtime", {})
    if not model_path:
        model_path = str(cfg.get("model_path") or "") or None
    if not context:
        try:
            context = int(cfg.get("context_size") or 65536)
        except Exception:
            context = 65536
    name = Path(model_path).name if model_path else None
    quant = infer_quant(Path(model_path)) if model_path else None
    return {
        "model_path": model_path,
        "model_name": name,
        "quantization": quant,
        "context_capacity": context,
        "args": args,
    }


def sync_runtime_sessions() -> None:
    """Track every local llama-server process without assuming it was launched by this app."""
    live: dict[tuple[int, int], tuple[psutil.Process, dict[str, Any]]] = {}
    for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
        try:
            name = (proc.info.get("name") or "").lower()
            cmd = " ".join(proc.info.get("cmdline") or []).lower()
            if "llama-server" not in f"{name} {cmd}":
                continue
            created = int(float(proc.info.get("create_time") or proc.create_time()))
            live[(proc.pid, created)] = (proc, _parse_runtime_args(proc))
        except Exception:
            continue

    seen_ids: set[int] = set()
    now = now_iso()
    with db() as conn:
        open_rows = conn.execute("SELECT * FROM runtime_sessions WHERE ended_at IS NULL").fetchall()
        open_by_key = {(int(r["pid"]), int(float(r["process_started_at"] or 0))): r for r in open_rows}

        for (pid, created), (proc, meta) in live.items():
            row = open_by_key.get((pid, created))
            if row and (row["model_path"] or "") != (meta.get("model_path") or ""):
                conn.execute(
                    "UPDATE runtime_sessions SET ended_at=?, last_seen_at=?, close_reason=? WHERE id=?",
                    (now, now, "model_changed", row["id"]),
                )
                row = None
            if row:
                seen_ids.add(int(row["id"]))
                conn.execute(
                    "UPDATE runtime_sessions SET last_seen_at=?, model_name=?, model_path=?, quantization=?, context_capacity=?, runtime_json=? WHERE id=?",
                    (now, meta.get("model_name"), meta.get("model_path"), meta.get("quantization"), meta.get("context_capacity"), json.dumps({"args": meta.get("args", [])}, ensure_ascii=False), row["id"]),
                )
            else:
                started = _iso_from_epoch(float(proc.create_time()))
                cur = conn.execute(
                    "INSERT INTO runtime_sessions(pid,process_started_at,source,model_name,model_path,quantization,context_capacity,runtime_json,started_at,last_seen_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (pid, created, "detected", meta.get("model_name"), meta.get("model_path"), meta.get("quantization"), meta.get("context_capacity"), json.dumps({"args": meta.get("args", [])}, ensure_ascii=False), started, now),
                )
                seen_ids.add(int(cur.lastrowid))

        for row in open_rows:
            if int(row["id"]) in seen_ids:
                continue
            # Close at the last confirmed heartbeat, not "now". This avoids counting PC-off time.
            end = row["last_seen_at"] or now
            conn.execute(
                "UPDATE runtime_sessions SET ended_at=?, close_reason=? WHERE id=?",
                (end, "process_missing", row["id"]),
            )


async def runtime_tracker_loop(interval: float = 5.0) -> None:
    while True:
        try:
            await asyncio.to_thread(sync_runtime_sessions)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(interval)


def _streak_stats(day_tokens: dict[str, int]) -> tuple[int, int]:
    active = sorted(datetime.fromisoformat(k).date() for k, v in day_tokens.items() if v > 0)
    if not active:
        return 0, 0
    active_set = set(active)
    longest = 1
    cur = 1
    for a, b in zip(active, active[1:]):
        if (b - a).days == 1:
            cur += 1
            longest = max(longest, cur)
        elif b != a:
            cur = 1
    today = _local_now().date()
    current = 0
    d = today
    while d in active_set:
        current += 1
        d -= timedelta(days=1)
    # If today has not been used yet, report the streak ending yesterday.
    if current == 0:
        d = today - timedelta(days=1)
        while d in active_set:
            current += 1
            d -= timedelta(days=1)
    return current, longest


def get_usage_summary(period: str = "1m") -> dict[str, Any]:
    if period not in RANGE_DAYS:
        period = "1m"
    start = _period_start(period)
    start_iso = start.isoformat(timespec="seconds") if start else None
    now = _local_now()

    with db() as conn:
        if start_iso:
            runs = conn.execute("SELECT * FROM inference_runs WHERE started_at>=? ORDER BY started_at ASC", (start_iso,)).fetchall()
            runtime_rows = conn.execute("SELECT * FROM runtime_sessions WHERE COALESCE(ended_at,last_seen_at)>=? ORDER BY started_at ASC", (start_iso,)).fetchall()
        else:
            runs = conn.execute("SELECT * FROM inference_runs ORDER BY started_at ASC").fetchall()
            runtime_rows = conn.execute("SELECT * FROM runtime_sessions ORDER BY started_at ASC").fetchall()

    total_prompt = 0
    total_output = 0
    total_inference = 0.0
    total_generation = 0.0
    gen_weight_tokens = 0
    prompt_weight_tokens = 0
    prompt_eval_seconds = 0.0
    models: dict[str, dict[str, Any]] = {}
    clients: dict[str, dict[str, Any]] = {}
    daily: dict[str, dict[str, Any]] = defaultdict(lambda: {"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0, "requests": 0, "inference_seconds": 0.0})
    longest_run = None

    for r in runs:
        p = int(r["prompt_tokens"] or 0)
        o = int(r["output_tokens"] or 0)
        dur = float(r["total_duration"] or 0)
        gdur = float(r["generation_duration"] or 0)
        total_prompt += p
        total_output += o
        total_inference += dur
        total_generation += gdur
        if gdur > 0 and o > 0:
            gen_weight_tokens += o
        if r["prompt_tps"] and p > 0:
            prompt_eval_seconds += p / float(r["prompt_tps"])
            prompt_weight_tokens += p

        dt = _parse_iso(r["started_at"])
        day = dt.date().isoformat() if dt else "unknown"
        d = daily[day]
        d["prompt_tokens"] += p
        d["output_tokens"] += o
        d["total_tokens"] += p + o
        d["requests"] += 1
        d["inference_seconds"] += dur

        model_key = str(r["model_path"] or r["model_name"] or "Unknown")
        m = models.setdefault(model_key, {
            "model_name": r["model_name"] or Path(model_key).name,
            "model_path": r["model_path"],
            "quantization": r["quantization"],
            "prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0, "requests": 0,
            "inference_seconds": 0.0, "generation_seconds": 0.0, "tps_sum": 0.0, "tps_count": 0,
            "first_used": r["started_at"], "last_used": r["started_at"], "loaded_seconds": 0.0,
        })
        m["prompt_tokens"] += p
        m["output_tokens"] += o
        m["total_tokens"] += p + o
        m["requests"] += 1
        m["inference_seconds"] += dur
        m["generation_seconds"] += gdur
        if r["generation_tps"]:
            m["tps_sum"] += float(r["generation_tps"])
            m["tps_count"] += 1
        m["last_used"] = r["started_at"]

        ckey = str(r["client"] or "unknown")
        c = clients.setdefault(ckey, {"client": ckey, "prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0, "requests": 0, "inference_seconds": 0.0})
        c["prompt_tokens"] += p
        c["output_tokens"] += o
        c["total_tokens"] += p + o
        c["requests"] += 1
        c["inference_seconds"] += dur

        if longest_run is None or dur > float(longest_run.get("total_duration") or 0):
            longest_run = dict(r)

    server_uptime = 0.0
    longest_runtime = None
    runtime_timeline: list[dict[str, Any]] = []
    for rr in runtime_rows:
        rs = _parse_iso(rr["started_at"])
        re = _parse_iso(rr["ended_at"])
        seconds = _clip_seconds(rs, re, start, now)
        if seconds <= 0:
            continue
        server_uptime += seconds
        key = str(rr["model_path"] or rr["model_name"] or "Unknown")
        m = models.setdefault(key, {
            "model_name": rr["model_name"] or Path(key).name,
            "model_path": rr["model_path"], "quantization": rr["quantization"],
            "prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0, "requests": 0,
            "inference_seconds": 0.0, "generation_seconds": 0.0, "tps_sum": 0.0, "tps_count": 0,
            "first_used": rr["started_at"], "last_used": rr["last_seen_at"], "loaded_seconds": 0.0,
        })
        m["loaded_seconds"] += seconds
        timeline_item = {
            "id": rr["id"], "pid": rr["pid"], "model_name": rr["model_name"], "model_path": rr["model_path"],
            "quantization": rr["quantization"], "context_capacity": rr["context_capacity"],
            "started_at": rr["started_at"], "ended_at": rr["ended_at"], "last_seen_at": rr["last_seen_at"],
            "duration_seconds": seconds, "close_reason": rr["close_reason"],
        }
        runtime_timeline.append(timeline_item)
        if longest_runtime is None or seconds > longest_runtime["duration_seconds"]:
            longest_runtime = timeline_item

    model_list = []
    for m in models.values():
        m["avg_generation_tps"] = (m["tps_sum"] / m["tps_count"]) if m["tps_count"] else None
        m["weighted_generation_tps"] = (m["output_tokens"] / m["generation_seconds"]) if m["generation_seconds"] > 0 else None
        m["idle_loaded_seconds"] = max(0.0, m["loaded_seconds"] - m["inference_seconds"])
        m.pop("tps_sum", None); m.pop("tps_count", None)
        model_list.append(m)
    model_list.sort(key=lambda x: (x["total_tokens"], x["loaded_seconds"]), reverse=True)
    client_list = sorted(clients.values(), key=lambda x: x["total_tokens"], reverse=True)

    daily_list = [{"date": k, **v} for k, v in sorted(daily.items()) if k != "unknown"]
    day_tokens = {x["date"]: int(x["total_tokens"]) for x in daily_list}
    current_streak, longest_streak = _streak_stats(day_tokens)
    most_active_day = max(daily_list, key=lambda x: x["total_tokens"], default=None)

    total_tokens = total_prompt + total_output
    avg_gen_tps = (gen_weight_tokens / total_generation) if total_generation > 0 and gen_weight_tokens else None
    avg_prompt_tps = (prompt_weight_tokens / prompt_eval_seconds) if prompt_eval_seconds > 0 else None
    idle_loaded = max(0.0, server_uptime - total_inference)

    return {
        "period": period,
        "period_start": start_iso,
        "period_end": now.isoformat(timespec="seconds"),
        "summary": {
            "total_tokens": total_tokens,
            "prompt_tokens": total_prompt,
            "output_tokens": total_output,
            "requests": len(runs),
            "server_uptime_seconds": server_uptime,
            "inference_seconds": total_inference,
            "generation_seconds": total_generation,
            "idle_loaded_seconds": idle_loaded,
            "avg_generation_tps": avg_gen_tps,
            "avg_prompt_tps": avg_prompt_tps,
            "models_used": len([m for m in model_list if m["requests"] or m["loaded_seconds"]]),
            "current_streak_days": current_streak,
            "longest_streak_days": longest_streak,
        },
        "daily": daily_list,
        "models": model_list,
        "clients": client_list,
        "runtime_timeline": list(reversed(runtime_timeline[-100:])),
        "most_active_day": most_active_day,
        "longest_inference": dict(longest_run) if longest_run else None,
        "longest_runtime": longest_runtime,
    }
