from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .config import DATA_DIR, ensure_dirs

DB_PATH = DATA_DIR / "telemetry.db"
_lock = threading.RLock()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@contextmanager
def db():
    ensure_dirs()
    with _lock:
        conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                client TEXT NOT NULL,
                mode TEXT NOT NULL,
                model_name TEXT,
                model_path TEXT,
                context_capacity INTEGER NOT NULL DEFAULT 65536,
                context_used INTEGER NOT NULL DEFAULT 0,
                context_source TEXT NOT NULL DEFAULT 'estimated',
                settings_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                meta_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS inference_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                client TEXT NOT NULL,
                mode TEXT NOT NULL,
                model_name TEXT,
                model_path TEXT,
                quantization TEXT,
                context_capacity INTEGER,
                context_used INTEGER,
                prompt_tokens INTEGER,
                output_tokens INTEGER,
                prompt_tps REAL,
                generation_tps REAL,
                peak_tps REAL,
                prompt_duration REAL,
                generation_duration REAL,
                total_duration REAL,
                gpu_json TEXT NOT NULL DEFAULT '[]',
                cpu_percent REAL,
                ram_used_gb REAL,
                runtime_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'complete',
                started_at TEXT NOT NULL,
                ended_at TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS runtime_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pid INTEGER NOT NULL,
                process_started_at REAL,
                source TEXT NOT NULL DEFAULT 'external',
                model_name TEXT,
                model_path TEXT,
                quantization TEXT,
                context_capacity INTEGER,
                runtime_json TEXT NOT NULL DEFAULT '{}',
                started_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                ended_at TEXT,
                close_reason TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_runtime_sessions_started ON runtime_sessions(started_at);
            CREATE INDEX IF NOT EXISTS idx_runtime_sessions_model ON runtime_sessions(model_path, model_name);
            CREATE INDEX IF NOT EXISTS idx_inference_runs_started ON inference_runs(started_at);
            CREATE INDEX IF NOT EXISTS idx_inference_runs_model ON inference_runs(model_path, model_name);

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT NOT NULL,
                source TEXT NOT NULL,
                message TEXT NOT NULL,
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            """
        )


def create_session(title: str, client: str = "web", mode: str = "chat", context_capacity: int = 65536,
                   model_name: str | None = None, model_path: str | None = None, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    sid = str(uuid.uuid4())
    ts = now_iso()
    with db() as conn:
        conn.execute(
            "INSERT INTO sessions(id,title,client,mode,model_name,model_path,context_capacity,settings_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (sid, title, client, mode, model_name, model_path, context_capacity, json.dumps(settings or {}), ts, ts),
        )
    return get_session(sid)  # type: ignore[return-value]


def get_session(session_id: str) -> dict[str, Any] | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["settings"] = json.loads(d.pop("settings_json") or "{}")
    return d


def list_sessions(limit: int = 100) -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        d["settings"] = json.loads(d.pop("settings_json") or "{}")
        out.append(d)
    return out


def update_session(session_id: str, **fields: Any) -> None:
    allowed = {"title", "client", "mode", "model_name", "model_path", "context_capacity", "context_used", "context_source", "settings_json"}
    clean = {k: v for k, v in fields.items() if k in allowed}
    if not clean:
        return
    clean["updated_at"] = now_iso()
    cols = ",".join(f"{k}=?" for k in clean)
    values = list(clean.values()) + [session_id]
    with db() as conn:
        conn.execute(f"UPDATE sessions SET {cols} WHERE id=?", values)


def add_message(session_id: str, role: str, content: str, meta: dict[str, Any] | None = None) -> int:
    ts = now_iso()
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO messages(session_id,role,content,meta_json,created_at) VALUES(?,?,?,?,?)",
            (session_id, role, content, json.dumps(meta or {}, ensure_ascii=False), ts),
        )
        conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (ts, session_id))
        return int(cur.lastrowid)


def get_messages(session_id: str, limit: int = 500) -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id=? ORDER BY id ASC LIMIT ?", (session_id, limit)
        ).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        d["meta"] = json.loads(d.pop("meta_json") or "{}")
        out.append(d)
    return out


def delete_session(session_id: str) -> None:
    with db() as conn:
        conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))


def log_event(level: str, source: str, message: str, details: dict[str, Any] | None = None) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO events(level,source,message,details_json,created_at) VALUES(?,?,?,?,?)",
            (level, source, message, json.dumps(details or {}, ensure_ascii=False), now_iso()),
        )


def list_events(limit: int = 200) -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        d["details"] = json.loads(d.pop("details_json") or "{}")
        out.append(d)
    return out


def start_inference_run(payload: dict[str, Any]) -> int:
    cols = [
        "session_id", "client", "mode", "model_name", "model_path", "quantization", "context_capacity",
        "context_used", "prompt_tokens", "output_tokens", "prompt_tps", "generation_tps", "peak_tps",
        "prompt_duration", "generation_duration", "total_duration", "gpu_json", "cpu_percent", "ram_used_gb",
        "runtime_json", "status", "started_at", "ended_at"
    ]
    defaults = {
        "gpu_json": "[]", "runtime_json": "{}", "status": "running", "started_at": now_iso(), "ended_at": None,
        "client": "web", "mode": "chat"
    }
    values = []
    for c in cols:
        v = payload.get(c, defaults.get(c))
        if c in {"gpu_json", "runtime_json"} and not isinstance(v, str):
            v = json.dumps(v or ([] if c == "gpu_json" else {}), ensure_ascii=False)
        values.append(v)
    placeholders = ",".join("?" for _ in cols)
    with db() as conn:
        cur = conn.execute(f"INSERT INTO inference_runs({','.join(cols)}) VALUES({placeholders})", values)
        return int(cur.lastrowid)


def finish_inference_run(run_id: int, **fields: Any) -> None:
    allowed = {
        "context_used", "prompt_tokens", "output_tokens", "prompt_tps", "generation_tps", "peak_tps",
        "prompt_duration", "generation_duration", "total_duration", "gpu_json", "cpu_percent", "ram_used_gb",
        "runtime_json", "status", "ended_at"
    }
    clean = {k: v for k, v in fields.items() if k in allowed}
    if "gpu_json" in clean and not isinstance(clean["gpu_json"], str):
        clean["gpu_json"] = json.dumps(clean["gpu_json"], ensure_ascii=False)
    if "runtime_json" in clean and not isinstance(clean["runtime_json"], str):
        clean["runtime_json"] = json.dumps(clean["runtime_json"], ensure_ascii=False)
    clean.setdefault("ended_at", now_iso())
    cols = ",".join(f"{k}=?" for k in clean)
    with db() as conn:
        conn.execute(f"UPDATE inference_runs SET {cols} WHERE id=?", list(clean.values()) + [run_id])


def list_inference_runs(limit: int = 200, client: str | None = None) -> list[dict[str, Any]]:
    with db() as conn:
        if client:
            rows = conn.execute("SELECT * FROM inference_runs WHERE client=? ORDER BY id DESC LIMIT ?", (client, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM inference_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        for key in ("gpu_json", "runtime_json"):
            try:
                raw = d.pop(key)
                default = "[]" if key == "gpu_json" else "{}"
                d[key[:-5] if key.endswith("_json") else key] = json.loads(raw or default)
            except Exception:
                d[key[:-5]] = [] if key == "gpu_json" else {}
        out.append(d)
    return out
