# Source upload checkpoint — 17 October 2026

Destination: https://github.com/Diska404/Private_Ecosystem_Web

## Prepared scope

- Existing Ecosystem 2.1.0 source, including Hub, Local AI and SignalDeck, preserved as an independent Git repository.
- Repository-local author/committer identity: Diska404 with the account's GitHub no-reply email. Cached credentials were verified against the GitHub `/user` API before pushing. No global account setting was changed.
- `.gitignore` expanded for local configuration, environment files, databases, histories, logs, backups, ownership/control tokens and model/dependency files.
- Sanitized `config/app.example.json`; the real local `config/app.json` is excluded and left in place.
- Staged-source credential/database audit under `scripts/audit_publish.py`.
- Portable combined launcher source and installation guide under `workspace-launcher/`.
- Account workflow documented in `docs/GITHUB_WORKFLOW.md`.

## Executed validation

- Ecosystem registry/identity/ownership tests: 11/11 PASS.
- SignalDeck collector/storage tests: 5/5 PASS.
- Tuning editor JavaScript tests: 6/6 PASS.
- Three-process integration smoke: PASS for temporary dynamic ports, discovery, repeated start, authorized shutdown, draft-only capabilities, explicit DEMO data, CSV, offline state, individual start/stop, restart all and normal cleanup.
- Combined launcher tests: 7/7 PASS; real BAT start/reuse/status PASS; repeated launch kept the same four listening PIDs.
- Exact staged snapshot publish audit: PASS; rerun before each push.
- Actual local config, service tokens and telemetry database confirmed ignored by Git.

## Limits and continuation

The integration smoke uses isolated temporary databases and labeled DEMO sensor data, not evidence of physical tuning or every real sensor. This repository has local test evidence; no ecosystem-specific hosted Actions workflow is introduced in this checkpoint. The upload does not host the web app or expose its loopback services. Hardware Apply remains disabled. Existing long-run, driver reset, hotplug and overhead checks remain open.

The repository was public when audited. Publishing status is verified through the remote branch SHA after the push; this file records source preparation and local evidence, not a claim that every future CI job passes.

Run the three applications with `START-EKOSISTEM.bat`. Run all four including DevPulse with the installed `START-SEMUA-WEB.bat` in the common parent folder. See `workspace-launcher/README.md` for reinstalling the combined launcher after clone.
