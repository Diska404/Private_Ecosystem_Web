from __future__ import annotations

import asyncio
import os
import shlex
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import psutil

from .config import LOG_DIR, load_config, save_config, resolve_llama_server
from .database import log_event


class RuntimeManager:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.process: subprocess.Popen | None = None
        self.stdout_handle = None
        self.started_by_us = False
        self.last_command: list[str] = []
        self.last_error: str | None = None

    def config(self) -> dict[str, Any]:
        return load_config()["runtime"]

    def build_command(self, runtime: dict[str, Any] | None = None) -> list[str]:
        cfg = load_config()
        rt = dict(cfg["runtime"])
        if runtime:
            rt.update(runtime)
        exe = resolve_llama_server({**cfg, "runtime": rt})
        if not exe:
            raise RuntimeError("llama-server tidak ditemukan. Atur path executable di Settings / Runtime.")
        model = str(rt.get("model_path") or "").strip()
        if not model:
            raise RuntimeError("Model GGUF belum dipilih.")
        if not Path(model).exists():
            raise RuntimeError(f"Model tidak ditemukan: {model}")

        cmd = [exe, "-m", model, "--host", str(rt.get("host", "127.0.0.1")), "--port", str(rt.get("port", 8080))]
        cmd += ["-c", str(int(rt.get("context_size", 65536)))]

        ngl = rt.get("gpu_layers", "auto")
        if str(ngl).lower() == "auto":
            cmd += ["-ngl", "auto"]
        else:
            cmd += ["-ngl", str(int(ngl))]

        main_gpu = rt.get("main_gpu")
        if main_gpu is not None:
            cmd += ["--main-gpu", str(int(main_gpu))]
        tensor_split = str(rt.get("tensor_split") or "").strip()
        if tensor_split:
            cmd += ["--tensor-split", tensor_split]
        if rt.get("flash_attention", True):
            cmd += ["--flash-attn", "on"]
        else:
            cmd += ["--flash-attn", "off"]

        if rt.get("cache_type_k"):
            cmd += ["--cache-type-k", str(rt["cache_type_k"])]
        if rt.get("cache_type_v"):
            cmd += ["--cache-type-v", str(rt["cache_type_v"])]
        if rt.get("mtp"):
            cmd += ["--spec-type", "draft-mtp"]
        else:
            cmd += ["--spec-type", "none"]

        cmd += ["-b", str(int(rt.get("batch_size", 2048))), "-ub", str(int(rt.get("ubatch_size", 512)))]
        cmd += ["--parallel", str(int(rt.get("parallel", 1)))]
        if rt.get("fit", True):
            cmd += ["--fit", "on", "--fit-target", str(int(rt.get("fit_target_mib", 1536)))]
        cmd += ["--metrics", "--jinja"]

        extra = str(rt.get("extra_args") or "").strip()
        if extra:
            cmd.extend(shlex.split(extra, posix=False))
        return cmd

    def find_external_llama(self) -> list[psutil.Process]:
        found = []
        for p in psutil.process_iter(["name", "cmdline"]):
            try:
                blob = ((p.info.get("name") or "") + " " + " ".join(p.info.get("cmdline") or [])).lower()
                if "llama-server" in blob:
                    found.append(p)
            except Exception:
                pass
        return found

    def is_managed_running(self) -> bool:
        with self.lock:
            return bool(self.process and self.process.poll() is None)

    def status(self) -> dict[str, Any]:
        cfg = self.config()
        managed = None
        with self.lock:
            if self.process and self.process.poll() is None:
                try:
                    managed = {
                        "pid": self.process.pid,
                        "started_by_us": True,
                        "command": self.last_command,
                        "uptime_seconds": max(0, time.time() - psutil.Process(self.process.pid).create_time()),
                    }
                except Exception:
                    managed = {"pid": self.process.pid, "started_by_us": True, "command": self.last_command}
        external = []
        for p in self.find_external_llama():
            if managed and p.pid == managed.get("pid"):
                continue
            try:
                external.append({"pid": p.pid, "name": p.name(), "cmdline": " ".join(p.cmdline())})
            except Exception:
                pass
        return {
            "managed": managed,
            "external": external,
            "runtime": cfg,
            "last_error": self.last_error,
            "llama_server_path": resolve_llama_server(load_config()),
        }

    async def health(self, timeout: float = 1.2) -> dict[str, Any]:
        rt = self.config()
        url = f"http://{rt.get('host','127.0.0.1')}:{rt.get('port',8080)}"
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                r = await client.get(url + "/health")
                if 200 <= r.status_code < 300:
                    return {"ok": True, "status": r.status_code, "body": r.text[:500], "url": url}
            except Exception as first_error:
                r = None
                first_error_text = str(first_error)
            else:
                first_error_text = f"/health returned HTTP {r.status_code}"
            try:
                r2 = await client.get(url + "/v1/models")
                return {"ok": 200 <= r2.status_code < 300, "status": r2.status_code, "body": r2.text[:500], "url": url}
            except Exception as e:
                return {"ok": False, "error": f"{first_error_text}; /v1/models: {e}", "url": url}

    async def start(self, overrides: dict[str, Any] | None = None, wait_ready: bool = True) -> dict[str, Any]:
        with self.lock:
            if self.process and self.process.poll() is None:
                raise RuntimeError("Managed llama-server sudah berjalan.")
            if overrides:
                cfg = load_config()
                cfg["runtime"].update(overrides)
                save_config(cfg)
            cmd = self.build_command()
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            log_path = LOG_DIR / "llama-server.log"
            self.stdout_handle = open(log_path, "a", encoding="utf-8", buffering=1)
            self.stdout_handle.write(f"\n\n===== START {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
            self.stdout_handle.write("COMMAND: " + subprocess.list2cmdline(cmd) + "\n")
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self.process = subprocess.Popen(
                cmd,
                stdout=self.stdout_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                cwd=str(Path(cmd[0]).parent if Path(cmd[0]).exists() else Path.cwd()),
                creationflags=flags,
            )
            self.started_by_us = True
            self.last_command = cmd
            self.last_error = None
            pid = self.process.pid
            log_event("info", "runtime", "llama-server started", {"pid": pid, "command": cmd})

        if wait_ready:
            deadline = time.time() + 90
            while time.time() < deadline:
                await asyncio.sleep(0.7)
                with self.lock:
                    if not self.process or self.process.poll() is not None:
                        code = None if not self.process else self.process.returncode
                        self.last_error = f"llama-server berhenti saat startup (exit {code})."
                        raise RuntimeError(self.last_error)
                health = await self.health(timeout=0.8)
                if health.get("ok"):
                    return {"ok": True, "pid": pid, "health": health, "command": cmd}
            return {"ok": True, "pid": pid, "warning": "Server belum health-ready setelah 90 detik.", "command": cmd}
        return {"ok": True, "pid": pid, "command": cmd}

    async def stop(self, force: bool = False) -> dict[str, Any]:
        with self.lock:
            proc = self.process
        if not proc or proc.poll() is not None:
            return {"ok": True, "message": "Managed server tidak berjalan."}
        try:
            p = psutil.Process(proc.pid)
            if force:
                p.kill()
            else:
                p.terminate()
            try:
                p.wait(timeout=10)
            except psutil.TimeoutExpired:
                p.kill()
            log_event("info", "runtime", "llama-server stopped", {"pid": proc.pid, "force": force})
        finally:
            with self.lock:
                self.process = None
                if self.stdout_handle:
                    try:
                        self.stdout_handle.close()
                    except Exception:
                        pass
                    self.stdout_handle = None
        return {"ok": True}

    async def restart(self, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        await self.stop(force=False)
        await asyncio.sleep(0.5)
        return await self.start(overrides=overrides, wait_ready=True)

    def update_runtime_config(self, patch: dict[str, Any]) -> dict[str, Any]:
        cfg = load_config()
        cfg["runtime"].update(patch)
        save_config(cfg)
        return cfg["runtime"]


RUNTIME = RuntimeManager()
