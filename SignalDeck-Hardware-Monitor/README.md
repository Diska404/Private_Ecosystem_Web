> **Integrasi 2.1:** port aplikasi dan tautan ditentukan oleh `../ecosystem.json`. Gunakan launcher induk dan `KELOLA-EKOSISTEM.bat`; lihat README induk untuk aturan terbaru. Panduan standalone di bawah adalah dokumentasi aplikasi awal.

# SignalDeck — Hardware Monitor Lokal

Dashboard sensor *real-time* berbasis web, berjalan **hanya di komputer sendiri** (`127.0.0.1:8767`). Antarmuka bahasa Indonesia, tema gelap/terang, mode **Simple / Full**, halaman Overview/CPU/RAM/GPU/Disk/Jaringan/Sensor, grafik riwayat, dan ekspor CSV. Semua asset CSS/JS lokal: halaman tidak memerlukan internet setelah pemasangan.

## Menjalankan di Windows 11

1. Ekstrak ZIP ke folder biasa, misalnya `D:\SignalDeck`. **Jangan jalankan BAT dari dalam tampilan ZIP.**
2. Pastikan **Python 3.10 atau lebih baru** terpasang dan tersedia di PATH. Jika belum: https://www.python.org/downloads/windows/ (centang Add Python to PATH).
3. Klik dua kali **`MULAI.bat`**. Pertama kali dibutuhkan internet untuk memasang dependensi ke virtual environment `.venv` (otomatis; tidak mengubah paket Python global).
4. Browser akan membuka **http://127.0.0.1:8767**. Jika tidak terbuka otomatis, masukkan alamat itu secara manual. Biarkan jendela terminal tetap berjalan.
5. Untuk menghentikan, tekan `Ctrl+C` pada terminal atau tutup terminal.

### Sensor yang dibaca

| Sensor | Sumber | Persyaratan |
|---|---|---|
| CPU total/logical core, frekuensi | psutil | Otomatis |
| RAM, swap, pemakaian drive | psutil | Otomatis |
| Trafik jaringan & I/O disk | psutil | Otomatis; nilai laju baru stabil setelah beberapa sampel |
| NVIDIA RTX 4050 + eGPU RTX 5070 (load, VRAM, suhu, daya, clock, encoder) | NVIDIA NVML | Driver NVIDIA dan GPU terdeteksi; kemampuan spesifik tergantung driver dan perangkat |
| Intel UHD / adaptor lain | Windows Win32_VideoController | Nama adaptor otomatis; load dan suhu perlu LibreHardwareMonitor jika sensor tersedia |
| Suhu CPU, daya CPU, kipas, sensor board dan tambahan | LibreHardwareMonitor (LHM) | Aplikasi LHM berjalan dan menyediakan data melalui HTTP atau WMI |

**Tanpa LHM, suhu CPU dan kipas biasanya tidak tersedia di Windows.** Angka yang tidak tersedia ditampilkan `N/A`, bukan ditebak. Laptop/eGPU tertentu membatasi sensor tertentu, bahkan dengan LHM. **Penggunaan memori Intel UHD tidak dapat disamakan langsung dengan VRAM fisik diskret**; dapat saja `N/A`.

### Mengaktifkan sensor tambahan via LibreHardwareMonitor

1. Unduh **LibreHardwareMonitor** dari repositori resmi: https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases
2. Jalankan LibreHardwareMonitor; gunakan *Run as administrator* jika beberapa sensor tersembunyi.
3. Opsi yang direkomendasikan: aktifkan **Options → Remote Web Server**. Default `127.0.0.1:8085` harus merespons `/data.json`. Pastikan server LHM hanya bisa diakses dari perangkat yang Anda percaya; kalau tidak ingin mengaktifkan layanan jaringan, gunakan opsi WMI di bawah.
4. SignalDeck otomatis mencoba menghubungkan `http://127.0.0.1:8085/data.json` tiap beberapa detik.
5. Alternatif WMI: klik `AKTIFKAN-WMI-OPSIONAL.bat`. Lalu pastikan namespace `root\LibreHardwareMonitor` tersedia. Kompatibilitas WMI bergantung versi LHM.

Integrasi ini **opsional**. SignalDeck tetap berfungsi tanpa LHM untuk sensor standar dan NVIDIA.

Berkas `PREVIEW-DASHBOARD.png` memperlihatkan tampilan Full UI menggunakan data **simulasi**, bukan nilai sensor laptop Anda.

## Mode dan fitur

- **Simple:** ringkas untuk monitor sambil gaming/streaming.
- **Full:** seluruh analitik, mini grafik, grafik historis, panel sensor terperinci.
- Navigasi per hardware, pemilihan satu GPU (4050/5070/Intel) untuk inspeksi.
- Mode chart **Area / Line / Bar**, durasi **5 menit sampai 1 tahun**. Rekaman dimulai sejak aplikasi pertama kali dijalankan; data masa lalu tidak bisa diambil secara retrospektif.
- Riwayat SQLite disimpan **secara lokal** di `data/history.db` (`data/demo_history.db` untuk demo). Tingkatan resolusi: sampel mentah 48 jam, rata-rata 5 menit 90 hari, rata-rata per jam 365 hari. Diagram waktu panjang menampilkan rata-rata, bukan peak absolut.
- Lihat **session peaks** (beban CPU/RAM/GPU tertinggi selama aplikasi berjalan).
- Unduh CSV dari periode yang dipilih.
- Preferences mode, tema, pilihan grafik, periode, dan GPU disimpan oleh browser (`localStorage`), bukan dikirim keluar.
- **COBA-DEMO.bat**: menggunakan data simulasi dan dilabeli dengan jelas. **Jangan gunakan nilai demo untuk diagnostik.**

## Batasan / troubleshooting

- Server hanya listen pada `127.0.0.1` (bukan untuk akses dari HP/LAN).
- Dashboard adalah monitor read-only: **tidak** overclock/undervolt/ubah kipas/BIOS dan bukan pengganti validasi sensor HWiNFO64.
- NVIDIA eGPU harus tersambung dan dikenali sistem saat aplikasi berjalan. Untuk adaptor baru, restart SignalDeck agar namanya dibaca ulang; NVIDIA NVML dapat memerlukan restart setelah hotplug.
- Jika ada sensor kosong, periksa GPU aktif, driver, dukungan NVML dan status LibreHardwareMonitor di sidebar / halaman Sensor.
- Untuk Windows versi baru, WMI LHM tidak selalu stabil; lebih mudah gunakan Remote Web Server LHM jika tersedia.
- Jika `8767` dipakai aplikasi lain, ubah variabel lingkungan `SIGNALDECK_PORT` sebelum menjalankan.
- Data sensor tetap berada di laptop. Jangan mengekspos server ini melalui port forwarding atau proxy publik.
- Perhitungan pemakaian CPU oleh psutil adalah interval antar sampel, bukan analisis detail scheduling. Persentase Task Manager untuk GPU bisa berbeda definisi dari NVIDIA NVML.

## Pengujian

Untuk pengembang: `python -m pip install -r requirements.txt`, lalu `python -m unittest discover -s tests -v`. `SIGNALDECK_DEMO=1 python app.py` menjalankan mode demo. Backend mendukung Python 3.10+.


## Integrasi Local AI Control Center (v1.1)

- SignalDeck berjalan di **http://127.0.0.1:8767** (berbeda dari Local AI: 8765).
- Menu **Another Apps → Local AI Control Center** mengalihkan tab yang sama. Titik hijau berarti aplikasi tujuan terdeteksi aktif.
- Untuk paket gabungan, gunakan `START-KEDUANYA.bat` di folder induk; kedua server berjalan sebagai proses terpisah.
- `MULAI.bat` tetap bisa dijalankan secara mandiri.
- Port alternatif: atur environment variable `SIGNALDECK_PORT` dan `SIGNALDECK_AI_PORT` sebelum menjalankan (atau gunakan launcher gabungan).
- Jika port diubah secara manual, samakan nilai `signaldeck_port` pada `local-ai-control-center/config/app.json` agar menu bertaut benar.
