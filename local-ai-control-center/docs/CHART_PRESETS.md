# Chart Presets

## Telemetry Mix (default)
- Generation: Wave / area
- Context: Gauge
- GPU 0: Wave
- GPU 1: Donut
- RAM: Bar
- Usage token trend: Wave
- Usage models: Bar
- Usage clients: Donut

Tujuan: langsung memperlihatkan bahwa dashboard tidak terikat pada satu bentuk diagram.

## Wave Focus
Dominan wave/area untuk melihat perubahan resource dan inference secara realtime.

## Performance Lines
Dominan line/sparkline untuk pembacaan teknis yang rapat dan mudah membandingkan perubahan.

## Capacity
Gauge, donut, dan bar untuk fokus kapasitas Context/VRAM/RAM.

## Minimal
Line dan bar sederhana untuk penggunaan harian dengan visual yang lebih tenang.

## Custom
Setiap widget dapat diubah sendiri dari Chart Studio. Pilihan saat ini mencakup wave, line, step, dots, gauge, donut, dan bar. Klik **Save Visualization** untuk menyimpan ke `config/app.json`.
