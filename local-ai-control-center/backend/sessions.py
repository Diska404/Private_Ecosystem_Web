from __future__ import annotations

import hashlib
import json
from typing import Any

from . import database as db


def external_session_key(client: str, model: str | None, messages: list[dict[str, Any]]) -> str:
    # Stable enough for an external chat: first user message usually remains in every subsequent request.
    first_user = ""
    first_system = ""
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if isinstance(content, list):
            content = json.dumps(content, ensure_ascii=False)
        if role == "system" and not first_system:
            first_system = str(content)[:800]
        if role == "user" and not first_user:
            first_user = str(content)[:1200]
            break
    raw = f"{client}|{model or ''}|{first_system}|{first_user}".encode("utf-8", errors="ignore")
    return "ext-" + hashlib.sha1(raw).hexdigest()[:24]


def ensure_external_session(client: str, model: str | None, messages: list[dict[str, Any]], context_capacity: int) -> dict[str, Any]:
    sid = external_session_key(client, model, messages)
    existing = db.get_session(sid)
    if existing:
        db.update_session(sid, model_name=model, context_capacity=context_capacity)
        return db.get_session(sid) or existing
    title = "External session"
    for m in messages:
        if m.get("role") == "user":
            c = m.get("content", "")
            if isinstance(c, str) and c.strip():
                title = c.strip().replace("\n", " ")[:72]
                break
    ts = db.now_iso()
    with db.db() as conn:
        conn.execute(
            "INSERT INTO sessions(id,title,client,mode,model_name,context_capacity,context_source,settings_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (sid, title, client, "external", model, context_capacity, "runtime", "{}", ts, ts),
        )
    return db.get_session(sid) or {"id": sid, "title": title}


def context_summary(session: dict[str, Any]) -> dict[str, Any]:
    cap = int(session.get("context_capacity") or 0)
    used = int(session.get("context_used") or 0)
    return {
        "capacity": cap,
        "used": used,
        "remaining": max(0, cap - used) if cap else 0,
        "percent": round((used / cap * 100), 2) if cap else 0,
        "source": session.get("context_source", "estimated"),
    }
