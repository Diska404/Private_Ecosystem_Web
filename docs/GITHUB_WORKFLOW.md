# GitHub source checkpoint

Repository: https://github.com/Diska404/Private_Ecosystem_Web

The initial source upload uses the **Diska404** account. Git author and credential username are configured locally for this repository; global Git settings are left unchanged.

```powershell
git config --local user.name Diska404
git config --local user.email 115615910+Diska404@users.noreply.github.com
git config --local credential.https://github.com.username Diska404
```

The repository was public when prepared. Only source, tests, reference assets and documentation are intended for upload. Databases, chat/telemetry history, local configuration, service ownership tokens, logs, backups, model files and virtual environments stay on the local machine. `local-ai-control-center/config/app.example.json` is a sanitized example; the application creates its own local `app.json` when absent.

After staging changes, inspect exactly what will be committed:

```powershell
git diff --cached --stat
py -3 scripts/audit_publish.py
```

The pattern scan is a guard against common leaks, not proof that every possible secret can be recognized. Inspect newly added data/config files before committing them.

## Clone and run

For the combined workspace launcher, preserve the folder names:

```powershell
git clone https://github.com/Diska404/Private_Ecosystem_Web.git "Ecosystem v2.0"
git clone https://github.com/Diska404/Projek_Portofolio.git "DevWev Portofolio"
```

Run `START-EKOSISTEM.bat` inside the ecosystem folder for its three services. See `workspace-launcher/README.md` for the optional launcher that also starts DevPulse.

## College and personal accounts

The owner confirmed this account split: **Diska404 for college**; **RaizeiID for personal, YouTube and GFL2 Bahasa Indonesia**. Personal repositories use their own repository-local Git identity and credential username. No personal destination repository has been selected or uploaded in this checkpoint. Do not copy access tokens into repository files, remote URLs or chat.

## Release boundary

This is source versioning, not web hosting or a production release. Servers remain loopback-only. Hardware Tuning Studio remains a draft editor without physical hardware writes. Long-running sensor/driver/hotplug validation remains open.
