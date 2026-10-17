from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ecosystem import registry, apps_status, identity, authorized_shutdown, VERSION

import httpx
import uvicorn
from fastapi import Body, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .agent import agent_stream
from .config import ROOT, CONFIG_FILE, load_config, save_config, resolve_llama_server
from .database import (
    add_message,
    create_session,
    delete_session,
    get_messages,
    get_session,
    init_db,
    list_events,
    list_inference_runs,
    list_sessions,
    update_session,
)
from .gateway import fetch_models, runtime_base_url, stream_chat_request, complete_chat
from .models import scan_models
from .runtime import RUNTIME
from .sessions import context_summary, ensure_external_session
from .telemetry import STATE, snapshot
from .usage import get_usage_summary, runtime_tracker_loop, sync_runtime_sessions

app = FastAPI(title="Local AI Control Center", version=VERSION)
_USAGE_TRACKER_TASK = None
_SERVER = None
FRONTEND = ROOT / "frontend"

CONTEXT_PRESETS = [1024, 2048, 4096, 8192, 16384, 32768, 65536, 131072]


@app.on_event("startup")
async def startup() -> None:
    global _USAGE_TRACKER_TASK
    init_db()
    await asyncio.to_thread(sync_runtime_sessions)
    _USAGE_TRACKER_TASK = asyncio.create_task(runtime_tracker_loop())


@app.on_event("shutdown")
async def shutdown() -> None:
    global _USAGE_TRACKER_TASK
    if _USAGE_TRACKER_TASK:
        _USAGE_TRACKER_TASK.cancel()
        try:
            await _USAGE_TRACKER_TASK
        except BaseException:
            pass
        _USAGE_TRACKER_TASK = None


@app.get("/api/health")
async def api_health():
    return {"ok": True, "time": time.time(), **identity('ai')}


@app.get('/api/ecosystem/apps')
async def api_ecosystem_apps():
    return await asyncio.to_thread(apps_status)


@app.get('/ecosystem-nav.js')
async def ecosystem_nav_js():
    return FileResponse(ROOT.parent / 'ecosystem-nav.js', headers={'Cache-Control':'no-store'})


@app.get('/ecosystem-nav.css')
async def ecosystem_nav_css():
    return FileResponse(ROOT.parent / 'ecosystem-nav.css', headers={'Cache-Control':'no-store'})


@app.post('/api/ecosystem/shutdown', status_code=202)
async def ecosystem_shutdown(request: Request):
    if not authorized_shutdown(request.headers) or _SERVER is None:
        raise HTTPException(403, 'Launcher ownership required')
    _SERVER.should_exit = True
    return {'ok': True}


@app.get("/api/apps/bridge")
async def api_apps_bridge():
    data = await asyncio.to_thread(apps_status)
    return {'hub': data['apps']['hub'], 'signaldeck': data['apps']['signaldeck']}

@app.get("/api/status")
async def api_status():
    cfg = load_config()
    return {
        "runtime": RUNTIME.status(),
        "runtime_health": await RUNTIME.health(),
        "config": cfg,
        "context_presets": CONTEXT_PRESETS,
        "llama_server_path": resolve_llama_server(cfg),
    }


@app.get("/api/telemetry")
async def api_telemetry():
    data = snapshot()
    data["runtime"] = RUNTIME.status()
    data["runtime_health"] = await RUNTIME.health(timeout=0.6)
    return data


@app.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket):
    await ws.accept()
    cfg = load_config()
    interval = max(0.2, int(cfg.get("app", {}).get("telemetry_interval_ms", 500)) / 1000.0)
    try:
        while True:
            data = snapshot()
            data["runtime"] = RUNTIME.status()
            # Avoid a network health probe every 500 ms; process/log telemetry is enough here.
            await ws.send_json(data)
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        return
    except Exception:
        try:
            await ws.close()
        except Exception:
            pass


@app.get("/api/models")
async def api_models():
    return {"models": await asyncio.to_thread(scan_models)}


@app.post("/api/models/scan-paths")
async def api_model_paths(payload: dict[str, Any] = Body(...)):
    paths = payload.get("paths")
    if not isinstance(paths, list):
        raise HTTPException(400, "paths harus array")
    cfg = load_config()
    cfg["models"]["scan_paths"] = [str(x) for x in paths if str(x).strip()]
    save_config(cfg)
    return {"ok": True, "paths": cfg["models"]["scan_paths"]}


@app.get("/api/runtime")
async def api_runtime():
    return {"status": RUNTIME.status(), "health": await RUNTIME.health(), "presets": CONTEXT_PRESETS}


@app.post("/api/runtime/config")
async def api_runtime_config(payload: dict[str, Any] = Body(...)):
    allowed = {
        "llama_server_path", "host", "port", "model_path", "context_size", "gpu_layers", "main_gpu",
        "tensor_split", "cache_type_k", "cache_type_v", "flash_attention", "mtp", "batch_size",
        "ubatch_size", "parallel", "fit", "fit_target_mib", "extra_args",
    }
    patch = {k: v for k, v in payload.items() if k in allowed}
    if "context_size" in patch:
        ctx = int(patch["context_size"])
        if ctx < 1024 or ctx > 131072:
            raise HTTPException(400, "Context harus antara 1K dan 128K")
        patch["context_size"] = ctx
    rt = RUNTIME.update_runtime_config(patch)
    return {"ok": True, "runtime": rt, "restart_required": bool(patch)}


@app.post("/api/runtime/start")
async def api_runtime_start(payload: dict[str, Any] | None = Body(default=None)):
    try:
        return await RUNTIME.start(payload or {})
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/runtime/stop")
async def api_runtime_stop(payload: dict[str, Any] | None = Body(default=None)):
    return await RUNTIME.stop(force=bool((payload or {}).get("force")))


@app.post("/api/runtime/restart")
async def api_runtime_restart(payload: dict[str, Any] | None = Body(default=None)):
    try:
        return await RUNTIME.restart(payload or {})
    except Exception as e:
        raise HTTPException(400, str(e))


@app.get("/api/sessions")
async def api_sessions():
    sessions = list_sessions(200)
    for s in sessions:
        s["context"] = context_summary(s)
    return {"sessions": sessions}


@app.post("/api/sessions")
async def api_create_session(payload: dict[str, Any] = Body(...)):
    cfg = load_config()
    rt = cfg["runtime"]
    session = create_session(
        title=str(payload.get("title") or "New Chat")[:100],
        client=str(payload.get("client") or "web-chat"),
        mode=str(payload.get("mode") or "chat"),
        context_capacity=int(payload.get("context_capacity") or rt.get("context_size", 65536)),
        model_name=payload.get("model_name"),
        model_path=payload.get("model_path") or rt.get("model_path"),
        settings=payload.get("settings") or {},
    )
    session["context"] = context_summary(session)
    return session


@app.get("/api/sessions/{session_id}")
async def api_get_session(session_id: str):
    s = get_session(session_id)
    if not s:
        raise HTTPException(404, "Session tidak ditemukan")
    s["messages"] = get_messages(session_id)
    s["context"] = context_summary(s)
    return s


@app.patch("/api/sessions/{session_id}")
async def api_patch_session(session_id: str, payload: dict[str, Any] = Body(...)):
    if not get_session(session_id):
        raise HTTPException(404, "Session tidak ditemukan")
    allowed = {"title", "client", "mode", "model_name", "model_path", "context_capacity", "context_used", "context_source"}
    update_session(session_id, **{k: v for k, v in payload.items() if k in allowed})
    s = get_session(session_id)
    if s:
        s["context"] = context_summary(s)
    return s


@app.delete("/api/sessions/{session_id}")
async def api_delete_session(session_id: str):
    delete_session(session_id)
    return {"ok": True}


@app.post("/api/chat/{session_id}")
async def api_chat(session_id: str, payload: dict[str, Any] = Body(...)):
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session tidak ditemukan")
    user_message = str(payload.get("message") or "").strip()
    if not user_message:
        raise HTTPException(400, "message kosong")
    add_message(session_id, "user", user_message)
    messages = [{"role": m["role"], "content": m["content"]} for m in get_messages(session_id)]
    model = payload.get("model") or session.get("model_name") or "local-model"
    request_payload = {
        "model": model,
        "messages": messages,
        "temperature": float(payload.get("temperature", 0.7)),
        "top_p": float(payload.get("top_p", 0.95)),
        "max_tokens": int(payload.get("max_tokens", 4096)),
        "stream": True,
    }

    async def generator():
        assistant_text = ""
        async for raw in stream_chat_request(request_payload, "web-chat", session_id=session_id, persist_external_session=False):
            # Capture content while preserving upstream-compatible SSE for the UI.
            try:
                line = raw.decode("utf-8", errors="ignore").strip()
                if line.startswith("data:"):
                    data_text = line[5:].strip()
                    if data_text and data_text != "[DONE]":
                        obj = json.loads(data_text)
                        choices = obj.get("choices") or []
                        if choices:
                            delta = (choices[0].get("delta") or {}).get("content")
                            if delta:
                                assistant_text += delta
            except Exception:
                pass
            yield raw
        if assistant_text.strip():
            add_message(session_id, "assistant", assistant_text)

    return StreamingResponse(generator(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/agent/{session_id}")
async def api_agent(session_id: str, payload: dict[str, Any] = Body(...)):
    message = str(payload.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "message kosong")
    profile = str(payload.get("permission_profile") or load_config().get("agent", {}).get("permission_profile", "safe"))

    async def generator():
        async for event in agent_stream(session_id, message, profile):
            yield f"data: {event}\n\n".encode("utf-8")
        yield b"data: [DONE]\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/history")
async def api_history(limit: int = 200, client: str | None = None):
    return {"runs": list_inference_runs(min(max(limit, 1), 1000), client)}


@app.get("/api/usage")
async def api_usage(range: str = "1m"):
    await asyncio.to_thread(sync_runtime_sessions)
    return await asyncio.to_thread(get_usage_summary, range.lower())


@app.get("/api/events")
async def api_events(limit: int = 200):
    return {"events": list_events(min(max(limit, 1), 1000))}


@app.get("/api/logs/llama")
async def api_llama_log(tail: int = 250):
    log = ROOT / "logs" / "llama-server.log"
    hermes = Path(os.path.expandvars(load_config().get("clients", {}).get("hermes_log", "")))
    target = log if log.exists() else hermes
    if not target.exists():
        return {"path": None, "text": ""}
    try:
        lines = target.read_text(encoding="utf-8", errors="ignore").splitlines()[-min(max(tail, 20), 2000):]
        return {"path": str(target), "text": "\n".join(lines)}
    except Exception as e:
        return {"path": str(target), "text": f"ERROR: {e}"}


@app.get("/api/config")
async def api_config_get():
    return load_config()


@app.post("/api/config")
async def api_config_set(payload: dict[str, Any] = Body(...)):
    cfg = load_config()
    # Only shallow top-level known sections; frontend sends complete sub-sections.
    for section in ("app", "models", "clients", "agent", "charts"):
        if isinstance(payload.get(section), dict):
            cfg[section].update(payload[section])
    save_config(cfg)
    return cfg


# -------------------- OpenAI-compatible gateway --------------------

@app.get("/gateway/{client}/v1/models")
async def gateway_models(client: str):
    client = client.lower()
    if client not in {"hermes", "openclaw", "web"}:
        raise HTTPException(404, "Unknown client")
    STATE.mark_client(client)
    status, body, headers = await fetch_models()
    return Response(content=body, status_code=status, media_type=headers.get("content-type", "application/json"))


@app.post("/gateway/{client}/v1/chat/completions")
async def gateway_chat(client: str, payload: dict[str, Any] = Body(...)):
    client = client.lower()
    if client not in {"hermes", "openclaw", "web"}:
        raise HTTPException(404, "Unknown client")
    client_name = client if client != "web" else "web-chat"
    if payload.get("stream", False):
        return StreamingResponse(
            stream_chat_request(payload, client_name),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    session = ensure_external_session(client_name, str(payload.get("model") or "local-model"), payload.get("messages") or [], int(load_config()["runtime"].get("context_size", 65536)))
    try:
        obj = await complete_chat(payload, client_name, session_id=session.get("id"))
        return JSONResponse(obj)
    except Exception as e:
        raise HTTPException(503, str(e))


@app.api_route("/gateway/{client}/v1/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def gateway_generic(client: str, rest: str, request: Request):
    client = client.lower()
    if client not in {"hermes", "openclaw", "web"}:
        raise HTTPException(404, "Unknown client")
    STATE.mark_client(client)
    url = runtime_base_url() + "/v1/" + rest
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in {"host", "content-length"}}
    async with httpx.AsyncClient(timeout=120) as http:
        r = await http.request(request.method, url, content=body, headers=headers)
    return Response(content=r.content, status_code=r.status_code, media_type=r.headers.get("content-type"))


# -------------------- Frontend --------------------

app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.get("/")
async def root():
    return FileResponse(FRONTEND / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/{path:path}")
async def spa(path: str):
    # Keep frontend routing simple: unknown non-API paths return the SPA.
    if path.startswith("api/") or path.startswith("gateway/"):
        raise HTTPException(404)
    return FileResponse(FRONTEND / "index.html", headers={"Cache-Control": "no-store"})


def run() -> None:
    global _SERVER
    cfg = load_config()
    host = '127.0.0.1'
    port = registry()['ai']['port']
    if cfg["app"].get("open_browser", True) and os.environ.get("LOCAL_AI_NO_BROWSER", "0") != "1":
        import threading
        def _open():
            time.sleep(1.2)
            webbrowser.open(f"http://{host}:{port}")
        threading.Thread(target=_open, daemon=True).start()
    _SERVER = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level='warning', timeout_graceful_shutdown=8))
    _SERVER.run()


if __name__ == "__main__":
    run()
