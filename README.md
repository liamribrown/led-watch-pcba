# LED analogue watch PCBA

A wristwatch board that shows the time like an analogue watch, with LEDs in place of hands.
It stays dark until you press a button or tilt your wrist, then shows the time for about 5 seconds.

- **Board:** round, 38 mm, 4 layers, 1.0 mm. 60 amber 0402 LEDs on the outer ring (minutes) and
  12 red 0603 LEDs on the inner ring (hours), charlieplexed from 9 pins of an ATtiny3217.
  CR2032 coin cell, 32.768 kHz crystal for the clock, LIS2DH12 accelerometer for tilt-to-wake,
  two side buttons. Designed in KiCad 9 and generated from Python.
- **Firmware:** C for the ATtiny3217 (the pin-compatible ATtiny1617 also fits), with host unit tests.
- **Simulator:** a 3D model of the board plus a working watch that runs the real firmware logic
  compiled to WebAssembly: https://ai.liambrown.uk/watch/

## Status

Designed and reviewed on paper, **not yet built or tested on hardware.** Don't order boards
you aren't prepared to debug. Open points are in `projects/led-watch/SPEC.md` ("As built" and
the review tables at the end) and in `docs/reviews/`.

## Layout

| Path | What |
|---|---|
| `projects/led-watch/SPEC.md` | Requirements, decisions, as-built notes, BOM with LCSC parts |
| `projects/led-watch/PINMAP.md` | Pin map and LED table (the source of truth for firmware) |
| `projects/led-watch/tools/` | Python that generates the schematic and board (`generate.py`), plus the coin-cell safety check |
| `projects/led-watch/led-watch.kicad_*` | Generated KiCad project |
| `projects/led-watch/export.sh` | ERC/DRC gate, then gerbers, JLCPCB BOM and placement files |
| `projects/led-watch/firmware/` | Firmware, tests, build and flash scripts (see its README) |
| `projects/watch-sim/` | The browser simulator |
| `docs/reviews/` | Independent design reviews of the spec and board |

## Build it

```bash
# Board: needs KiCad 9 (kicad-cli). Stops on any ERC/DRC or coin-cell check failure.
projects/led-watch/export.sh

# Firmware: needs gcc (host tests) and avr-gcc.
cd projects/led-watch/firmware && ./build.sh
```

## Notes

- **Coin cell:** the board has a copper keep-out under the cell, enforced by
  `tools/check_cell.py`. Order plugged (filled) vias. 3.3 V SerialUPDI adapters only: a 5 V one
  would push current into the cell. In a case, the cell should only be reachable with a tool.
- **Cost (JLCPCB quote, 2026-11-12):** 10 assembled boards, both sides, about US$231 before
  shipping. Check part rotations in JLCPCB's placement preview before paying.
- **Stock:** the ATtiny3217 and the B3U-3100P buttons were low in stock on LCSC when the BOM
  was checked. The ATtiny1617 is the fallback chip.
- The documents were written by a small team of AI agents working under one person's direction,
  so they refer to "000" (the human) and agent numbers (003 Hardware, 004 Firmware, 007 Review).

## Licence

Software (firmware, simulator, generator scripts): **MIT**. Hardware design and documents:
**CERN-OHL-P-2.0**. Which folder is which is in [`LICENSE`](LICENSE); the texts are in `LICENSES/`.
