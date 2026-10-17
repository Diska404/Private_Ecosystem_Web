from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

import httpx
from fastapi import HTTPException

from .config import load_config
from .database import finish_inference_run, start_inference_run, update_session
from .models import infer_quant
from .sessions import ensure_external_session
from .telemetry import LOG_PARSER, STATE, get_gpus, get_system


def runtime_base_url() -> str:
    rt = load_config()["runtime"]
    return f"http://{rt.get('host','127.0.0.1')}:{rt.get('port',8080)}"


def runtime_model_info() -> dict[str, Any]:
    rt = load_config()["runtime"]
    model_path = str(rt.get("model_path") or "")
    name = model_path.replace("\\", "/").split("/")[-1] if model_path else None
    return {
        "model_path": model_path or None,
        "model_name": name,
        "quantization": infer_quant(__import__('pathlib').Path(model_path)) if model_path else None,
        "context_capacity": int(rt.get("context_size", 65536)),
        "runtime": rt,
    }


async def fetch_models() -> tuple[int, bytes, dict[str, str]]:
    async with httpx.AsyncClient(timeout=4) as client:
        try:
            r = await client.get(runtime_base_url() + "/v1/models")
            return r.status_code, r.content, dict(r.headers)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"llama-server tidak terhubung: {e}")


async def stream_chat_request(
    payload: dict[str, Any],
    client_name: str,
    session_id: str | None = None,
    persist_external_session: bool = True,
) -> AsyncIterator[bytes]:
    info = runtime_model_info()
    messages = payload.get("messages") or []
    model = payload.get("model") or info["model_name"] or "local-model"
    record_model = info["model_name"] or str(model)

    if session_id is None and persist_external_session:
        session = ensure_external_session(client_name, str(model), messages, info["context_capacity"])
        session_id = session["id"]

    req = dict(payload)
    req["stream"] = True
    # llama.cpp supports OpenAI stream usage on recent builds; harmless if ignored.
    opts = dict(req.get("stream_options") or {})
    opts["include_usage"] = True
    req["stream_options"] = opts

    started = time.time()
    prompt_tokens = None
    completion_tokens = None
    accumulated_text = ""
    first_token_at = None
    status = "complete"

    run_id = start_inference_run({
        "session_id": session_id,
        "client": client_name,
        "mode": "external" if client_name in {"hermes", "openclaw"} else ("agent" if client_name == "web-agent" else "chat"),
        "model_name": record_model,
        "model_path": info["model_path"],
        "quantization": info["quantization"],
        "context_capacity": info["context_capacity"],
        "runtime_json": info["runtime"],
        "status": "running",
    })
    STATE.mark_client(client_name, +1)

    try:
        timeout = httpx.Timeout(connect=10, read=None, write=30, pool=10)
        async with httpx.AsyncClient(timeout=timeout) as http:
            async with http.stream("POST", runtime_base_url() + "/v1/chat/completions", json=req) as r:
                if r.status_code >= 400:
                    body = await r.aread()
                    status = "error"
                    yield b"data: " + json.dumps({"error": body.decode(errors="ignore"), "status": r.status_code}).encode() + b"\n\n"
                    return

                async for line in r.aiter_lines():
                    if not line:
                        continue
                    raw = (line + "\n\n").encode("utf-8")
                    if line.startswith("data:"):
                        data_text = line[5:].strip()
                        if data_text != "[DONE]":
                            try:
                                obj = json.loads(data_text)
                                usage = obj.get("usage") or {}
                                if usage:
                                    prompt_tokens = usage.get("prompt_tokens", prompt_tokens)
                                    completion_tokens = usage.get("completion_tokens", completion_tokens)
                                choices = obj.get("choices") or []
                                if choices:
                                    delta = (choices[0].get("delta") or {}).get("content")
                                    if delta:
                                        if first_token_at is None:
                                            first_token_at = time.time()
                                        accumulated_text += delta
                            except Exception:
                                pass
                    yield raw
    except Exception as e:
        status = "error"
        yield b"data: " + json.dumps({"error": str(e)}).encode() + b"\n\n"
    finally:
        ended = time.time()
        STATE.mark_client(client_name, -1)
        timing = LOG_PARSER.parse()
        gen_tps = timing.get("generation_tps")
        prompt_tps = timing.get("prompt_tps")
        if completion_tokens is None:
            completion_tokens = timing.get("generated_tokens")
        if prompt_tokens is None:
            prompt_tokens = timing.get("prompt_tokens")
        if prompt_tokens is not None:
            STATE.set_context(client_name, int(prompt_tokens), info["context_capacity"], "runtime")
            if session_id:
                update_session(session_id, context_used=int(prompt_tokens), context_capacity=info["context_capacity"], context_source="runtime", model_name=record_model, model_path=info["model_path"])
        system = get_system()
        finish_inference_run(
            run_id,
            context_used=prompt_tokens,
            prompt_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            prompt_tps=prompt_tps,
            generation_tps=gen_tps,
            generation_duration=(ended - first_token_at) if first_token_at else None,
            total_duration=ended - started,
            gpu_json=get_gpus(),
            cpu_percent=system.get("cpu_percent"),
            ram_used_gb=system.get("ram_used_gb"),
            status=status,
        )


async def complete_chat(payload: dict[str, Any], client_name: str = "web-agent", session_id: str | None = None) -> dict[str, Any]:
    req = dict(payload)
    req["stream"] = False
    info = runtime_model_info()
    model = payload.get("model") or info["model_name"] or "local-model"
    record_model = info["model_name"] or str(model)
    started = time.time()
    run_id = start_inference_run({
        "session_id": session_id,
        "client": client_name,
        "mode": "agent" if client_name == "web-agent" else "chat",
        "model_name": record_model,
        "model_path": info["model_path"],
        "quantization": info["quantization"],
        "context_capacity": info["context_capacity"],
        "runtime_json": info["runtime"],
        "status": "running",
    })
    STATE.mark_client(client_name, +1)
    status = "complete"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=180, write=30, pool=10)) as http:
            r = await http.post(runtime_base_url() + "/v1/chat/completions", json=req)
            if r.status_code >= 400:
                status = "error"
                raise RuntimeError(f"llama-server {r.status_code}: {r.text[:1000]}")
            obj = r.json()
            usage = obj.get("usage") or {}
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            timing = LOG_PARSER.parse()
            if prompt_tokens is not None:
                STATE.set_context(client_name, int(prompt_tokens), info["context_capacity"], "runtime")
                if session_id:
                    update_session(session_id, context_used=int(prompt_tokens), context_capacity=info["context_capacity"], context_source="runtime", model_name=record_model, model_path=info["model_path"])
            system = get_system()
            finish_inference_run(
                run_id, context_used=prompt_tokens, prompt_tokens=prompt_tokens, output_tokens=completion_tokens,
                prompt_tps=timing.get("prompt_tps"), generation_tps=timing.get("generation_tps"),
                total_duration=time.time()-started, gpu_json=get_gpus(), cpu_percent=system.get("cpu_percent"),
                ram_used_gb=system.get("ram_used_gb"), status=status,
            )
            return obj
    except Exception:
        finish_inference_run(run_id, total_duration=time.time()-started, status="error")
        raise
    finally:
        STATE.mark_client(client_name, -1)
