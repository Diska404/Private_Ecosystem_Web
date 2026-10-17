# Changelog

## V1.2 — 2026-10-03

### Added
- Usage & Insights page with 1D/1W/1M/3M/6M/1Y/ALL filters.
- Token activity heatmap and streak stats.
- Runtime session heartbeat tracking.
- Model loaded time, inference time, idle-loaded time, and per-model token totals.
- Chart Studio with five presets.
- Custom per-widget chart types.
- Mixed dashboard visualization: wave, line, gauge, donut, bar, sparkline.
- Runtime timeline and per-model usage table.

### Changed
- Inference history records the actual loaded model filename when the runtime path is known.
- Config now persists a `charts` section.
- Database migration is additive; existing V1 history is preserved.
