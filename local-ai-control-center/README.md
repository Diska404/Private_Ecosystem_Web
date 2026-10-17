> **Integrasi 2.1:** port aplikasi dan tautan ditentukan oleh `../ecosystem.json`. Gunakan launcher induk dan `KELOLA-EKOSISTEM.bat`; lihat README induk untuk aturan terbaru. Panduan standalone di bawah adalah dokumentasi aplikasi awal.

# Local AI Control Center

**Build:** V1.2 Usage & Visualization Studio

Local-first dashboard untuk menjalankan, mengontrol, dan memonitor model GGUF melalui `llama-server`, dengan UI web lokal yang terinspirasi dari dashboard SIM Inventory milik pengguna.

## Fitur yang sudah ada

- Dashboard real-time via WebSocket.
- Monitoring CPU, RAM, RTX 4050, RTX 5070 (NVML, fallback `nvidia-smi`).
- Deteksi proses `llama-server`, Hermes, dan OpenClaw.
- Monitoring state inference (`IDLE`, `PROMPT`, `GENERATING`) dari log `llama-server` bila tersedia.
- Generation TPS dan Prompt TPS dari timing log llama.cpp.
- Grafik TPS dan GPU usage tanpa library frontend eksternal/CDN.
- Model library: scan file `.gguf` dari folder yang dikonfigurasi.
- Runtime manager: start / stop / restart `llama-server`.
- Context preset: 1K, 2K, 4K, 8K, 16K, 32K, 64K, 128K.
- Runtime options: GPU layers, main GPU, tensor split, KV cache, Flash Attention, MTP, batch/uBatch, parallel, fit target.
- Local Chat streaming via OpenAI-compatible llama.cpp API.
- Session persistence SQLite.
- Context usage tersimpan per session dari `prompt_tokens` runtime.
- Gateway untuk Hermes dan OpenClaw agar request bisa dimonitor:
  - `http://127.0.0.1:8765/gateway/hermes/v1`
  - `http://127.0.0.1:8765/gateway/openclaw/v1`
- Inference history: model, client, prompt/output token, context, TPS, duration, GPU/RAM snapshot.
- Performance page untuk membandingkan model/quant dari hasil aktual laptop sendiri.
- **Usage & Insights** dengan filter 1 Hari / 1 Minggu / 1 Bulan / 3 Bulan / 6 Bulan / 1 Tahun / Sepanjang Waktu.
- Activity heatmap token ala contribution/activity view.
- Statistik per model: loaded time, active inference, idle-loaded, input/output/total token, TPS, dan jumlah request.
- Runtime history otomatis untuk mencatat model apa yang dimuat dan berapa lama `llama-server` hidup.
- **Chart Studio** dengan preset `Telemetry Mix`, `Wave Focus`, `Performance Lines`, `Capacity`, dan `Minimal`.
- Bentuk visual dapat dikustom per widget: wave/area, line, step, dots, gauge, donut, dan bar.
- Local Agent **beta** dengan tool lokal dan permission profile:
  - Safe: read-only.
  - Standard: read + write file + launch app.
  - Full: termasuk PowerShell.

## Quick Start Windows

### Cara termudah

Double-click:

```text
START.bat
```

Script akan:

1. Membuat `.venv` bila belum ada.
2. Install dependency Python.
3. Menjalankan FastAPI.
4. Membuka browser ke:

```text
http://127.0.0.1:8765
```

### Via PowerShell

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\run.ps1
```

## Requirement

- Windows 11 direkomendasikan.
- Python 3.10+.
- NVIDIA Driver bila ingin telemetry GPU.
- `llama-server.exe` dari llama.cpp:
  - idealnya tersedia di `PATH`, atau
  - isi path-nya di **Runtime Settings**.

## Scan model default

Project sudah memasukkan folder berikut sebagai lokasi scan awal:

```text
Y:\GFL2_AI\models
Y:\GFL2_AI\models\hf-cache
C:\AI\models
D:\AI\models
```

Lokasi ini dapat diubah dari **Settings → Model scan paths**.

## Menjalankan model dari dashboard

1. Buka **Models**.
2. Klik **Use Model** pada `.gguf` utama.
3. Buka **Runtime Settings**.
4. Pilih context 1K–128K dan pengaturan lain.
5. Klik **Apply & Restart**.
6. Setelah health server aktif, buka **Local Chat**.

> File MTP sidecar kecil ditandai `mtp-sidecar` dan tidak ditawarkan sebagai model utama.

## Context Window

Context disimpan per session.

Contoh:

```text
Chat A  → 41K / 64K
Chat B  →  8K / 32K
Agent C → 27K / 64K
```

Saat kembali ke session lama, UI menampilkan context terakhir yang tercatat untuk session tersebut.

Untuk request melalui gateway Hermes/OpenClaw, Control Center membuat fingerprint session external dari isi conversation awal. Ini membantu memisahkan chat external tanpa membutuhkan modifikasi source Hermes/OpenClaw.

## Hermes

Agar telemetry Hermes lebih lengkap, arahkan OpenAI-compatible endpoint Hermes ke:

```text
http://127.0.0.1:8765/gateway/hermes/v1
```

Gateway meneruskan request ke llama-server di port runtime (default `8080`) sambil mencatat client, context, token, dan inference history.

Jika Hermes tetap memakai managed runtime sendiri, dashboard tetap mencoba mendeteksi process dan `%LOCALAPPDATA%\hermes\logs\llama-server.log`, tetapi data context breakdown akan lebih terbatas.

## OpenClaw

Gunakan endpoint:

```text
http://127.0.0.1:8765/gateway/openclaw/v1
```

Process juga dideteksi berdasarkan nama `openclaw` / `open-claw`.

## Local Agent Beta

Agent menggunakan tool calling OpenAI-compatible dari model lokal.

Permission profile:

### Safe

- List directory.
- Read text file.
- System info.
- List processes.

### Standard

Tambahan:

- Write text file.
- Launch app / open folder.

### Full Control

Tambahan:

- Run arbitrary PowerShell.

> `Full Control` sengaja tidak menjadi default. Gunakan hanya bila memahami konsekuensinya.

## Data yang disimpan

SQLite:

```text
data/telemetry.db
```

Menyimpan:

- sessions
- messages
- inference_runs
- runtime/control events
- runtime_sessions (server/model loaded time + heartbeat)

Log runtime yang dijalankan dashboard:

```text
logs/llama-server.log
```

## Runtime configuration

File konfigurasi:

```text
config/app.json
```

Context maksimal dibatasi UI menjadi 131072 / 128K sesuai scope proyek yang direncanakan.

## Catatan kompatibilitas llama.cpp

Flag runtime dapat berbeda antar build llama.cpp. Project memakai fitur modern seperti:

- `--metrics`
- `--jinja`
- `--flash-attn`
- `--cache-type-k`
- `--cache-type-v`
- `--spec-type draft-mtp`
- `--fit`

Jika build llama.cpp Anda lebih lama dan server gagal start, buka **Logs** dan hilangkan flag yang tidak didukung melalui `extra_args`/pengaturan runtime, atau update llama.cpp.

## Upgrade dari V1

Jika Anda sudah menguji V1 dan ingin mempertahankan history, **jangan hapus `data/telemetry.db`**. Salin/replace file program dari build baru ke folder lama. `init_db()` melakukan migrasi non-destruktif dengan menambahkan tabel/index baru bila belum ada.

Folder test seperti:

```text
C:\Users\Raizei\OneDrive\Documents\VSCODE 1\AI LOKAL\local-ai-control-center
```

boleh tetap digunakan. Saat nanti dipindahkan ke lokasi permanen, bawa folder `data/` bila ingin mempertahankan history Usage.

## Usage & Insights

Halaman **Usage & Insights** membedakan:

- **Server Uptime**: berapa lama proses `llama-server` terdeteksi hidup.
- **Model Loaded Time**: durasi model tertentu berada pada runtime.
- **Active Inference**: jumlah durasi request inference yang tercatat.
- **Idle-loaded**: server/model masih loaded tetapi tidak sedang inference.
- **Input Token / Output Token / Total Token**: diakumulasi per request dan per model.

Runtime tracker menggunakan PID + process start time + heartbeat. Jika proses hilang/crash, session ditutup pada heartbeat terakhir yang terkonfirmasi agar waktu PC mati tidak dihitung sebagai uptime.

## Chart Studio

Preset bawaan:

```text
Telemetry Mix      wave + gauge + donut + bar
Wave Focus         dominan wave/area
Performance Lines  dominan line/sparkline
Capacity           gauge/donut/bar
Minimal            tampilan sederhana
```

Setelah memilih preset, setiap widget masih dapat diubah sendiri. Klik **Save Visualization** agar konfigurasi disimpan di `config/app.json`.

## Arsitektur

```text
Web Chat ─────┐
Web Agent ────┤
Hermes ───────┼── Local AI Gateway ── llama-server ── RTX 5070 / RTX 4050 / RAM
OpenClaw ─────┘
```

Control Center adalah layer observability + runtime manager. Semua komponen tetap berjalan lokal pada `127.0.0.1` secara default.

## Folder penting

```text
backend/     FastAPI, runtime manager, gateway, telemetry, sessions, agent
frontend/    HTML/CSS/JavaScript dashboard
config/      konfigurasi aplikasi
data/        SQLite
logs/        llama-server log
docs/        referensi desain
```

## Status project

Build ini ditujukan sebagai **V1.2 functional foundation**, bukan mockup. Fitur Agent sudah dapat melakukan tool calling dasar, tetapi desktop vision/mouse/keyboard automation dan context compaction otomatis belum dimasukkan agar fondasi runtime/session/telemetry tetap stabil terlebih dahulu.


## Integrasi SignalDeck Hardware Monitor

Di sidebar **System → Another Apps → SignalDeck Hardware Monitor**, gunakan tautan untuk membuka dashboard sensor lengkap pada port **8767**. Indikator status diperbarui berkala.

- Local AI tetap di `http://127.0.0.1:8765` dan gateway Hermes/OpenClaw tidak diubah.
- SignalDeck berjalan sebagai layanan mandiri di `http://127.0.0.1:8767`.
- Gunakan `START-KEDUANYA.bat` dari direktori induk paket gabungan agar kedua backend aktif.
- Untuk port SignalDeck lain, tambahkan `"signaldeck_port": 8767` (atau port pilihan) ke objek `app` dalam `config/app.json`.
- Integrasi hanya menyediakan navigasi dan pemeriksaan kesehatan antaraplikasi, **tidak** menggabungkan data, sesi, atau hak akses kedua layanan.
