from __future__ import annotations

import asyncio
import json
import os
import platform
import shlex
import subprocess
from pathlib import Path
from typing import Any, AsyncIterator

import psutil

from .config import load_config
from .database import add_message, get_messages, get_session, update_session
from .gateway import complete_chat, runtime_model_info


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and folders in a local directory.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_text_file",
            "description": "Read a UTF-8/local text file. Use for source code, logs, configs, TSV/CSV, JSON and text documents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "max_chars": {"type": "integer", "minimum": 1000, "maximum": 100000},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "system_info",
            "description": "Read local CPU, RAM, OS, and running process summary.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_processes",
            "description": "List running processes, optionally filtered by name.",
            "parameters": {
                "type": "object",
                "properties": {"name_filter": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "launch_app",
            "description": "Launch a local Windows application or open a file/folder. Requires standard/full permission.",
            "parameters": {
                "type": "object",
                "properties": {"target": {"type": "string"}},
                "required": ["target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_text_file",
            "description": "Create or overwrite a local text file. Requires standard/full permission.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_powershell",
            "description": "Run a PowerShell command on the local computer. Requires full permission.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
]

PERMISSIONS = {
    "safe": {"list_directory", "read_text_file", "system_info", "list_processes"},
    "standard": {"list_directory", "read_text_file", "system_info", "list_processes", "launch_app", "write_text_file"},
    "full": {x["function"]["name"] for x in TOOL_SCHEMAS},
}


def _tool_allowed(name: str, profile: str) -> bool:
    return name in PERMISSIONS.get(profile, PERMISSIONS["safe"])


def execute_tool(name: str, args: dict[str, Any], profile: str) -> dict[str, Any]:
    if not _tool_allowed(name, profile):
        return {"ok": False, "error": f"Tool '{name}' diblokir oleh permission profile '{profile}'."}
    try:
        if name == "list_directory":
            p = Path(os.path.expandvars(os.path.expanduser(args["path"])))
            items = []
            for child in list(p.iterdir())[:500]:
                try:
                    st = child.stat()
                    items.append({
                        "name": child.name,
                        "path": str(child),
                        "type": "directory" if child.is_dir() else "file",
                        "size": st.st_size if child.is_file() else None,
                    })
                except Exception:
                    items.append({"name": child.name, "path": str(child), "type": "unknown"})
            return {"ok": True, "path": str(p), "items": items}

        if name == "read_text_file":
            p = Path(os.path.expandvars(os.path.expanduser(args["path"])))
            max_chars = max(1000, min(int(args.get("max_chars", 30000)), 100000))
            text = p.read_text(encoding="utf-8", errors="replace")
            return {"ok": True, "path": str(p), "content": text[:max_chars], "truncated": len(text) > max_chars}

        if name == "system_info":
            vm = psutil.virtual_memory()
            return {
                "ok": True,
                "os": platform.platform(),
                "cpu_logical": psutil.cpu_count(),
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "ram_used_gb": round((vm.total - vm.available) / (1024**3), 2),
                "ram_total_gb": round(vm.total / (1024**3), 2),
            }

        if name == "list_processes":
            needle = str(args.get("name_filter") or "").lower()
            rows = []
            for p in psutil.process_iter(["pid", "name", "memory_info"]):
                try:
                    pname = p.info["name"] or ""
                    if needle and needle not in pname.lower():
                        continue
                    rss = p.info["memory_info"].rss if p.info.get("memory_info") else 0
                    rows.append({"pid": p.pid, "name": pname, "ram_mb": round(rss / 1024**2, 1)})
                except Exception:
                    pass
            return {"ok": True, "processes": rows[:300]}

        if name == "launch_app":
            target = os.path.expandvars(os.path.expanduser(str(args["target"])))
            if os.name == "nt":
                os.startfile(target)  # type: ignore[attr-defined]
            else:
                subprocess.Popen([target])
            return {"ok": True, "launched": target}

        if name == "write_text_file":
            p = Path(os.path.expandvars(os.path.expanduser(args["path"])))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(str(args.get("content", "")), encoding="utf-8")
            return {"ok": True, "path": str(p), "bytes": p.stat().st_size}

        if name == "run_powershell":
            command = str(args["command"])
            timeout = int(load_config().get("agent", {}).get("tool_timeout_seconds", 30))
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            p = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                capture_output=True, text=True, timeout=timeout, creationflags=flags
            )
            return {
                "ok": p.returncode == 0,
                "exit_code": p.returncode,
                "stdout": p.stdout[-30000:],
                "stderr": p.stderr[-10000:],
            }

        return {"ok": False, "error": f"Unknown tool: {name}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def agent_stream(session_id: str, user_message: str, permission_profile: str | None = None) -> AsyncIterator[str]:
    session = get_session(session_id)
    if not session:
        yield json.dumps({"type": "error", "message": "Session tidak ditemukan."})
        return

    cfg = load_config()
    profile = permission_profile or cfg.get("agent", {}).get("permission_profile", "safe")
    max_steps = int(cfg.get("agent", {}).get("max_steps", 8))

    add_message(session_id, "user", user_message)
    history = get_messages(session_id)
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    system = {
        "role": "system",
        "content": (
            "You are a local computer agent running on the user's own Windows PC. "
            "Use tools only when needed. Be precise and do not claim an action succeeded unless the tool result says so. "
            f"Current permission profile: {profile}."
        ),
    }
    messages = [system] + messages

    yield json.dumps({"type": "status", "state": "planning", "profile": profile})
    final_text = ""
    usage_prompt = None

    for step in range(max_steps):
        payload = {
            "model": runtime_model_info().get("model_name") or "local-model",
            "messages": messages,
            "tools": TOOL_SCHEMAS,
            "tool_choice": "auto",
            "temperature": 0.4,
            "stream": False,
        }
        try:
            response = await complete_chat(payload, "web-agent", session_id=session_id)
        except Exception as e:
            yield json.dumps({"type": "error", "message": str(e)})
            return

        usage = response.get("usage") or {}
        if usage.get("prompt_tokens") is not None:
            usage_prompt = int(usage["prompt_tokens"])
        choices = response.get("choices") or []
        if not choices:
            yield json.dumps({"type": "error", "message": "Model tidak mengembalikan choices."})
            return
        msg = choices[0].get("message") or {}
        content = msg.get("content") or ""
        tool_calls = msg.get("tool_calls") or []

        if content:
            final_text += content
            yield json.dumps({"type": "assistant", "content": content, "step": step + 1})

        messages.append({
            "role": "assistant",
            "content": content or None,
            **({"tool_calls": tool_calls} if tool_calls else {}),
        })

        if not tool_calls:
            add_message(session_id, "assistant", final_text or content)
            if usage_prompt is not None:
                update_session(session_id, context_used=usage_prompt, context_source="runtime")
            yield json.dumps({"type": "done", "steps": step + 1, "context_used": usage_prompt})
            return

        for call in tool_calls:
            fn = (call.get("function") or {})
            name = fn.get("name")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}
            yield json.dumps({"type": "tool_call", "name": name, "arguments": args, "step": step + 1})
            result = await asyncio.to_thread(execute_tool, str(name), args, profile)
            yield json.dumps({"type": "tool_result", "name": name, "result": result, "step": step + 1})
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", f"tool-{step}"),
                "content": json.dumps(result, ensure_ascii=False),
            })

    add_message(session_id, "assistant", final_text or "Agent mencapai batas langkah sebelum menyelesaikan tugas.")
    yield json.dumps({"type": "done", "steps": max_steps, "warning": "max_steps_reached", "context_used": usage_prompt})
