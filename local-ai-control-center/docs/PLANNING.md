# Planning / Roadmap

## V1.2 — Implemented in this package

- Hardware telemetry
- llama-server detection + runtime manager
- Model library
- Context 1K–128K
- Local Chat streaming
- Session/context persistence
- Hermes/OpenClaw detection + gateway aliases
- SQLite inference logging
- **Usage & Insights**: 1D / 1W / 1M / 3M / 6M / 1Y / ALL
- Token activity heatmap
- Per-model token/input/output/runtime/inference/idle/TPS statistics
- Runtime session heartbeat and model-loaded history
- **Chart Studio**: mixed presets + per-widget visualization type
- Dashboard resource diagrams: donut / gauge / wave / bar / sparkline
- Usage diagrams: wave / line / step / bar / donut / heatmap / stacked runtime
- Performance analytics
- Local Agent beta + permission profiles

## V1.3 — Next

- Better per-request live TPS through `/metrics` counters when supported.
- Persist hardware samples for long-term GPU/VRAM/power graphs.
- Runtime boot progress parser.
- Runtime profiles (Balanced / Fast / Max Quality).
- Fork session + explicit model retokenization.
- Exact client context breakdown when system/tool messages are proxied.
- Export Usage/History to CSV/JSON.
- Drag/drop dashboard layout and user-created custom chart cards.

## V2

- Context compaction with preserved checkpoint/history.
- Tool approval modal (`Allow once`, `Deny`, `Always allow`).
- Browser automation via Playwright.
- Desktop screenshots + vision.
- Mouse/keyboard/window control.
- Agent background-task policy.
- Safer command policies and workspace allowlists.

## V3

- Automated model/quant benchmark suite.
- MTP acceptance-rate analytics.
- KV cache analytics.
- PCIe telemetry.
- Bottleneck detection and recommendations.
- Optional LAN mode with authentication.
