# Combined launcher checkpoint

Date: 17 October 2026, Asia/Jakarta

Entry point: `START-SEMUA-WEB.bat` in the parent Private WEB folder.

Files added: the entry BAT, `CARA-JALANKAN-SEMUA-WEB.txt`, `.web-launcher/launch_workspace.py`, `.web-launcher/RUN-DEVPULSE.bat`, `.web-launcher/test_launcher.py`, and this checkpoint.

Validated on Windows:

- Seven launcher identity/reuse/conflict unit checks passed.
- The BAT started DevPulse and reused the three already running ecosystem services.
- Repeating the default BAT succeeded, invoked browser opening, and preserved all four listening PIDs.
- `--status` reports all four services online, bound to 127.0.0.1.
- The DevPulse HTTP smoke passed seven pages, private dashboard redirect, owner API denial for seven methods, and reference asset/unknown route boundaries.
- A previously running DevPulse process returned HTTP 500 with missing Next dependency files. Its verified development processes were stopped, `npm ci --no-fund` restored the lockfile dependency tree, and the BAT successfully started a fresh preview. npm reported zero vulnerabilities.

Limits: a cold start of all three ecosystem services was not repeated during this launcher check; their existing lifecycle implementation is reused. DevPulse uses an interactive development terminal and stops with Ctrl+C. Ecosystem services use their existing service manager. An unknown/unhealthy port is reported as conflict and is never forcibly replaced. Product release gates and hardware-write restrictions remain unchanged.

Resume: double-click the BAT; use `--status` for read-only inspection. Preserve the helper and sibling project folders. The portable copy is versioned under `Ecosystem v2.0/workspace-launcher/`.

## CR001 — two portfolio audiences

The launcher now runs five services, adding the separate creator portfolio at 127.0.0.1:3101. The personal instance remains at 3100. Each portfolio must pass its own audience identity plus page/owner-boundary probes. Nine launcher tests pass, including cross-audience rejection. The BAT successfully started the creator in its own interactive terminal and reused the other four services. A repeated launch preserved all five listening PIDs; all listeners remain bound to 127.0.0.1. Helper added: RUN-CREATOR.bat. No application database/config/key is read by the launcher. The optional invitation setup belongs to the portfolio app.
