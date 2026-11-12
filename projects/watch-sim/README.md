# LED watch simulator

A browser simulation of the LED watch (`projects/led-watch`): a 3D board view (orbit/zoom, top and
bottom) with a working watch driven by the real firmware code. For `ai.liambrown.uk/watch/`.

**It simulates the firmware logic, not the electronics.** No currents, LED brightness, battery life or
crystal drift are modelled. The page says so, and every firmware number it shows (timeouts, thresholds,
LED/line/tick counts) is read from the compiled firmware (`sim_const`), which takes them from the headers.

## Files

| Path | What |
|---|---|
| `public/index.html`, `public/app.js` | The page: three.js r128 (cdnjs, pinned, SRI hash) + glue. Inline CSS, no other external resources. |
| `public/watch.wasm` | 5 KB. Real `ui.c timekeep.c clockface.c led_map.c tilt.c battery.c` (+ shared `core.c`) with a simulated hardware layer. Built by 004: `wasm/build-wasm.sh` (needs clang-19, lld-19). |
| `public/board-geometry.json` | Board outline, LED/part/button/battery positions from the PCB (003: `projects/led-watch/tools/export_3d.py`). Positions are exact; part bodies are simplified boxes. |
| `wasm/` | `sim.c` (hardware layer), `README.md` (the `sim_*` API), `test-sim.mjs` (node tests). |

## Run and test

    cd projects/watch-sim/public && python3 -m http.server 8765    # open http://localhost:8765
    ~/.local/node/bin/node projects/watch-sim/wasm/test-sim.mjs     # firmware-logic checks

Static files only (no server logic). If WebGL is unavailable the page falls back to a flat 2D top view;
the simulation works the same.

## Using it

The watch starts as after a battery change: set mode at 12:00. A steps the hour, B the minute (hold A + B
to enter set mode later). It saves after the idle timeout and sleeps; then A, or changing the wrist angle
to face-up (0°), shows the time. The supply-voltage slider below the empty threshold gives the low-battery blink.
Panels show the 9 charlieplex lines (driven high / low / floating) and the last scan frame.

## Notes

- Built against firmware commit e6fec48 on agent/004 (adds `core.c`, shared with the real `main.c`).
- No personal data: the JSON and wasm contain only geometry and logic.
