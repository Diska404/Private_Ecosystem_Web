# One BAT for the complete local workspace

This folder versions the combined launcher independently of local runtime files.

Expected layout after cloning the two repositories using the names in `docs/GITHUB_WORKFLOW.md`:

```text
Private WEB/
  START-SEMUA-WEB.bat
  CARA-JALANKAN-SEMUA-WEB.txt
  .web-launcher/
  Ecosystem v2.0/
  DevWev Portofolio/
```

Copy `START-SEMUA-WEB.bat`, `CARA-JALANKAN-SEMUA-WEB.txt`, and the complete `.web-launcher` folder from this distribution into the parent `Private WEB` folder. Keep the two project folder names as shown. Open that parent BAT. It starts or reuses Hub (8764), Local AI (8765), SignalDeck (8767), and DevPulse (3100), then opens their pages.

Do not run the distribution BAT inside this folder: it must be placed in the common parent folder. For this existing development workspace the files are already installed there.

Python 3.10+ and Node.js 20.9+/npm must be available. Dependency installation can require internet. The DevPulse terminal remains visible; stop it with Ctrl+C. Use the existing ecosystem manager to stop its three background services.

Read-only status: `START-SEMUA-WEB.bat --status`. Start without browser tabs: `START-SEMUA-WEB.bat --no-browser`. Checks and limitations are in `.web-launcher/CHECKPOINT.md`.
