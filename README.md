# LOCAL WORK & SETTING — Ecosystem 2.1.0

Tiga aplikasi lokal dalam proses terpisah: Ecosystem Hub, Local AI Control Center, dan SignalDeck Hardware Monitor. Pengembangan ini melanjutkan baseline 2.0; database dan konfigurasi model tetap milik masing-masing aplikasi.

Source repository: https://github.com/Diska404/Private_Ecosystem_Web . Identitas Git khusus akun kuliah, pengecualian data lokal, dan cara clone ada di `docs/GITHUB_WORKFLOW.md`. Launcher opsional yang juga menjalankan DevPulse tersedia di `workspace-launcher/` untuk disalin ke folder induk bersama.

## Menjalankan pada Windows

1. Buka `START-EKOSISTEM.bat` dari folder ini. Python 3.10+ diperlukan. Dependency dipasang ke `.venv` per aplikasi hanya jika belum tersedia; pemasangan awal memerlukan internet.
2. Browser membuka Hub. Layanan berjalan di background tanpa jendela terminal tambahan; menutup browser tidak menghentikan server.
3. Gunakan `KELOLA-EKOSISTEM.bat` untuk status, start, stop, restart, dan melihat log. Pintasan `BUKA-*.bat` membaca registry yang sama.

Perintah PowerShell dari folder induk:

```powershell
py -3 launch_all.py start
py -3 launch_all.py status
py -3 launch_all.py stop
py -3 launch_all.py restart
py -3 launch_all.py restart signaldeck --no-browser
py -3 launch_all.py logs ai
```

Log launcher ada di `logs/hub.log`, `logs/ai.log`, dan `logs/signaldeck.log`. Log runtime AI yang sudah ada tetap di folder aplikasi AI. Informasi ownership/token lokal berada di `.ecosystem/`; jangan bagikan folder ini. Tidak ada token kontrol di API health.

## Sumber konfigurasi layanan

`ecosystem.json` menjadi sumber nama/port layanan. Default: Hub 8764, AI 8765, SignalDeck 8767. Semua server hanya bind ke `127.0.0.1`.

Stop layanan sebelum mengedit registry, kemudian start kembali. Pengelola menolak menggandakan instance yang masih aktif di port lama. Nilai `app.port` dan `app.signaldeck_port` pada konfigurasi AI lama tidak lagi menentukan port server; nilai efektif di API mengikuti registry. Konfigurasi runtime llama-server (misalnya port 8080), model GGUF, chat, dan analytics tidak dipindahkan.

Override untuk pengujian/otomasi: `ECOSYSTEM_CONFIG`, `ECOSYSTEM_PORT`, `ECOSYSTEM_AI_PORT`, `ECOSYSTEM_SIGNALDECK_PORT`. Override lingkungan lebih tinggi prioritasnya daripada file. `SIGNALDECK_PORT` tetap diterima bila `ECOSYSTEM_SIGNALDECK_PORT` tidak disetel.

Identitas layanan mencakup service, versi, protocol ekosistem, instalasi, dan instance. Proses dari instalasi/versi berbeda atau pemilik port yang tidak cocok tidak diambil alih. `stop` mengirim permintaan shutdown ber-token ke instance yang dimulai launcher; tidak menjalankan taskkill atau menghentikan PID asing. Layanan yang dijalankan manual harus ditutup lewat terminal pemiliknya.

## Navigasi

Sidebar dan header ketiga aplikasi memperoleh URL/status melalui backend registry. Link membuka tab yang sama. Klik layanan offline atau instalasi berbeda menampilkan instruksi lokal dan mempertahankan halaman saat ini. Status diperiksa setiap 12 detik. Hub menampilkan PID, versi, readiness, dan label DEMO.

## Monitoring dan tuning

Monitoring menggunakan psutil, NVIDIA NVML, dan LibreHardwareMonitor opsional. Sensor tidak tersedia tetap `N/A`; demo selalu ditandai. Sampling backend sekitar 2 detik, refresh layar sekitar 2,2 detik. Belum ada benchmark overhead gaming/OBS.

Hardware Tuning Studio tetap **editor rancangan** dengan lima level. Fan curve dan voltage-frequency curve dapat digeser langsung atau melalui keyboard (panah; Shift memperbesar langkah), dengan batas monoton, Undo, reset, simpan lokal, dan impor/ekspor JSON. Range editor bukan safe range driver. Hardware Apply tetap terkunci; tidak ada endpoint tulis OC/UV.

Profil GPU baru menggunakan UUID NVML bila tersedia. Profil lama berbasis indeks tetap tersimpan dalam localStorage dan tidak otomatis dipasangkan dengan UUID karena urutan GPU dapat berubah. Verifikasi perangkat saat memindahkan profil lama. History monitoring tetap memakai ID lama agar riwayat yang ada tidak berubah; stabilitas ID history setelah hotplug masih perlu ditingkatkan.

## Data dan migrasi

Sebelum perubahan 2.1 pada workspace pengembangan, backup kode/config serta snapshot SQLite konsisten dibuat di `.backups/20261017-113705`. Folder ini hanya ada di mesin pengembangan dan tidak masuk ZIP.

Untuk migrasi dari instalasi lain: hentikan layanan lama, buat backup config dan database, lalu salin hanya data/config yang diperlukan ke aplikasi sejenis. Jangan menimpa source baru dengan backend/frontend lama atau menyalin WAL/SHM secara terpisah dari database aktif. Gunakan SQLite backup API jika database masih berjalan. `config/app.json` yang tidak valid sekarang ditolak dengan error; tidak diam-diam direset ke default.

## Pengujian dan paket

```powershell
py -3 -m unittest discover -s tests -v
.\SignalDeck-Hardware-Monitor\.venv\Scripts\python.exe -m unittest discover -s SignalDeck-Hardware-Monitor/tests -v
node --test tests/tuning.test.cjs
py -3 tests/integration_smoke.py
py -3 build_release.py
```

Integration smoke menjalankan tiga proses dengan port/database/log/ownership sementara, menggunakan **DEMO** untuk sensor. Ini tidak menggantikan pengujian sensor nyata. Suite JavaScript memakai Node bawaan dan tidak memerlukan npm install.

`build_release.py` menghasilkan ZIP dan SHA-256 di `dist/`. Paket tidak memasukkan `.venv`, database, WAL/SHM, backup, ownership/token, logs, laporan lokal, atau config pribadi. Konfigurasi distribusi dihasilkan dari default dengan path model kosong. Source/test dan asset lokal disertakan.

Status pengembangan: integrasi 2.1 dan perbaikan editor telah diterapkan. Pengujian panjang, hotplug/reset driver, detail sensor Intel/CPU, dan adapter tuning vendor belum selesai. Tidak ada klaim dukungan OC/UV fisik.
