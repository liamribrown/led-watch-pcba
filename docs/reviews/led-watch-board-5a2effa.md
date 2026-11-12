# Re-review: LED watch board rev A (agent/003 @ 5a2effa, board 1f5e4d9)

Reviewer: 007, 2026-11-11. Detached checkout of 5a2effa, kicad-cli 9.0.2, pcbnew Python.
Previous review: `led-watch-board-9cdeb82.md`.

**Verdict: APPROVED** for ordering rev A, with three non-blocking notes (N1-N3) and the
JLCPCB-preview rotation check (item 4) still to do at order time.

## Checks run

- `./export.sh`: ERC OK, DRC OK, cell check OK, BOM 14 lines / 99 parts, CPL 99 (94 top, 5 bottom).
  ERC and DRC at all severities with parity: 0 errors, 0 warnings, 0 violations, 0 unconnected.
- **1 [SAFETY] CR2032: fixed.** I checked this independently of `check_cell.py`, measuring the
  distance from each track *segment* to the centre, not just its end points:
  - no B.Cu track comes within r ≤ 10.5 mm;
  - the B.Cu GND fill starts at r = 10.49 mm (outline 0, r 10.49-18.7) and has nothing inside it;
  - the only B.Cu pads under the cell are BT1 pad 2 (GND) and the + tabs at r 11.45;
  - there are no VBAT or VDD vias under the cell. VBAT reaches Q1 on F.Cu (closest r 7.84) from a
    via at r 16.2, and its B.Cu run is an arc at r ≥ 10.7, at the can's own potential;
  - the 15 GND vias under the cell are all at r ≤ 1.32, inside pad 2;
  - no via under the cell keeps a B.Cu ring.
- **2 Pin map: fixed.** 004 @ 81f15c1 `board.h` matches the netlist: L0-L8 = PA3-PA7 then PB7-PB4,
  SW_A PC2, SW_B PC3, ACC_INT PC0, SCL PB0, SDA PB1, TX PA1, RTC PA2, UPDI PA0. `led_table.h`:
  all 72 bytes match the netlist's (anode, cathode) for D1-D72. PINMAP.md is the source of truth.
- **3:** four Ø1 mm B.Paste dots on pad 2 ✓ (see N1). I didn't check the tab pads against
  MY-CP-0209 myself; I'm taking 003's reading of the drawing.
- **4:** the `ROT_FIX` table and its list of parts to check are in export.sh ✓. It stays empty
  until the JLCPCB preview, so do that check before paying.
- **5, 8, 9:** in SPEC.md ✓.
- **6:** Y1 is vertical; inside its courtyard + 0.5 mm there's only XT1/XT2/GND copper on F.Cu,
  and no vias ✓.
- **7:** TP1-TP4 at y = 83.10, x = 96.19 / 98.73 / 101.27 / 103.81, exactly 2.54 mm pitch ✓.
- **Other changes:** U2 is rotated 180° with CS, SA0, Vdd and Vdd_IO all on VDD ✓. C2 is removed and
  VDD is decoupled by C3 22 µF + C1/C4 100 nF ✓ (enough, per spec review #8).

## Notes (non-blocking)

- **N1.** One GND via in pad 2, at (−1.30, −0.25) from the centre, overlaps the paste dot at
  (−1.9, 0): the centres are 0.65 mm apart against 0.75 mm of combined radii. Solder will wick into
  it and that dome will come out low. The other pad-2 vias are open in the mask opening too. Next
  time the board is generated, move that via ≥ 0.8 mm from the dot (or move the dot). The other
  three domes still give contact.
- **N2.** Signal vias under the cell's + rim (r 8.6-10.0): L8, L5, SW_A, SW_B, RTC, UPDI. They're
  tented with no B.Cu ring, so they aren't a cell short. But RTC and UPDI have no series resistor,
  so a mask defect would connect an MCU pin straight to the can. Order with **plugged/filled
  vias** (003 already plans to), or move these vias inside r < 8 in a later revision.
- **N3.** `check_cell.py` tests B.Cu tracks by their end points only, so a straight segment whose
  ends are both outside 10.5 mm but whose middle cuts across the keep-out would pass. My
  segment-distance check found none today. Use the distance from the segment to the centre in the
  script so it stays a reliable gate.
