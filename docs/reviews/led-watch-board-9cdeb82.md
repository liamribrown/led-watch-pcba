# Review: LED watch schematic + PCB rev A (agent/003 @ 9cdeb82)

Reviewer: 007, 2026-11-11. Checked on a detached checkout of 9cdeb82 in worktrees/007 with
kicad-cli 9.0.2 and pcbnew's Python API. I also read 004's firmware assumptions (agent/004 2ec9e5f).

**Verdict: not approved yet.** One safety fix is needed (P1: copper under the coin cell) and one
board/firmware pin-map mismatch must be resolved (P2, mainly 004's side). Everything else is minor
or a check to do at order time. Re-review after P1 is a quick look.

## What I ran and checked

- `./export.sh` → ERC OK, DRC OK. Gerbers (16 files), BOM 15 lines / 100 parts, CPL 100
  placements (95 top, 5 bottom), previews. Also ran ERC and DRC at **all severities** with schematic
  parity: 0 errors, 0 warnings, 0 unconnected, 0 footprint errors.
- **Netlist** (from the schematic): all 72 LEDs are unique ordered (anode, cathode) pairs of L0-L8,
  each line has 16 LED pins + its 100 Ω resistor, and none are duplicated or shorted. PINMAP.md's LED
  table matches the netlist on all 72 rows. The board's LED positions are clockwise from 12 at
  exactly 6°/30° steps (D1-D60 r = 17.30 mm, D61-D72 r = 9.60 mm). Every LED has its cathode on
  pad 1, consistently.
- **MCU pins** against my memory of the ATtiny3217 VQFN-24 pinout (PA2, PA3, GND, VDD, PA4-PA7,
  PB7-PB0, PC0-PC5, PA0, PA1 = pins 1-24, with the EP on GND): they match. TOSC1/2 = PB3/PB2 ✓,
  TWI0 PB0/PB1 ✓, TX on the alternate pin PA1 ✓, EVOUT0 on PA2 ✓, UPDI PA0 ✓, SW_A on PC2
  (async) ✓.
- **Spec items:** #1 ✓ (pads are UPDI, GND, TX and RTC; there is no VDD or VBAT test point
  anywhere in the netlist). #2 ✓ (case requirement). #5, #6, #8, #9, #10, #12 ✓ in the netlist and
  layout. #3, #4, #7 are firmware rules in PINMAP.md ✓. #11: Fab-layer polarity dots ✓.
- **LED drive:** 100 Ω × 2 per path; yellow 0402 and red 0603 AlInGaP at Vf ≈ 1.9-2.0 V gives
  ≈ 4 mA from a fresh cell and ≈ 2-3 mA from an old one, as in the spec review. Only one LED is
  ever on, so the per-pin current is 4 mA ✓.
- **Crystal load:** with 2 × 6.8 pF C0G + 5.5 pF pin capacitance + ≈ 0.5 pF trace per side,
  CL ≈ 12.8/2 + ≈ 0.5 ≈ 6.9 pF against the 7 pF part ✓. The XT1/XT2 traces are 3.8/5.2 mm ✓.
- **Reverse polarity:** AO3401A SOT-23 pin 1 G = GND, pin 2 S = VDD, pin 3 D = VBAT. That's
  the right way round: the body diode conducts from the cell, then the channel turns on. #13: from
  my memory of the AO3401A datasheet (I couldn't fetch it), Vgs(th) is −0.5 to −1.3 V and Rds(on)
  is ≤ 80 mΩ at −2.5 V. That agrees with 003's numbers. At 5 mA the drop is < 1 mV even at a
  2.4 V cell ✓.
- **Decoupling:** C1 100 nF ≈ 1.6 mm from U1 VDD ✓. C4 100 nF ≈ 3 mm from U2 Vdd/Vdd_IO
  (acceptable). Bulk C2 10 µF + C3 22 µF next to U1 ✓. Q1 is next to the bulk caps ✓.
- **LIS2DH12:** CS = VDD (I2C), SA0 = VDD (0x19), Res pin 5 = GND, INT2 NC, INT1 → PC0 ✓.
  The footprint is KiCad's generic LGA-12 2 × 2 mm (4 + 2 + 4 + 2 pads, 0.375 × 0.35 mm, 0.15 mm
  gaps). It's plausible for ST's land pattern, but I couldn't get to ST's drawing to compare pad
  sizes. (b): accepted as is, low risk.
- **QFN EP 2.6 × 2.6:** the KiCad footprint is generated from Microchip's packaging spec
  00000049BQ. My memory of the 4 × 4 VQFN-24 EP is 2.50-2.70 mm, nominal 2.60 ✓ (c).
- **Buttons (e):** on the bottom, at 2 and 4 o'clock (r = 16.45 mm). The actuator outline in the
  footprint (−Y) ends at r ≈ 19.4 mm, 0.4 mm past the 19.0 mm edge, so it points outwards ✓.
  The ground terminal is on GND, with 1 kΩ + 100 nF on the MCU side and the ESD footprint DNP ✓.
- **Fab rules:** 0.10 mm minimum clearance and track, vias 0.3/0.5 (149 of them, all tented),
  0.3 mm copper to edge, 1.0 mm 4-layer. All within JLCPCB's standard 4-layer process.
- **BOM/CPL generation:** DNP and test points are left out, the BOM count equals the CPL count,
  and every line has an LCSC number. The CPL Y coordinate is negated (KiCad convention; JLCPCB
  accepts it).

## Problems

1. **[SAFETY] Bottom copper under the CR2032 is separated from the cell only by solder mask.**
   The cell sits minus-face down on pad 2. A CR2032's minus face is the centre cap (≈ r < 8 mm),
   and the **plus can's crimped rim** is also on that face (≈ r 8.5-10 mm). On B.Cu:
   - **VBAT** (cell +, *before* Q1) runs on B.Cu under the minus face. For example, the segments
     (92.2, 96.7)→(96.3, 96.7)→(100.4, 92.6) reach r = 5.0 mm, and there are three VBAT vias at
     r = 6.4-7.4 mm.
   - The **GND pour** covers ≈ 90 % of the r 8.5-10 mm ring, right under the plus rim.
   - 16 GND, 5 VDD and other vias are tented under the cell. Tenting on 0.3 mm vias is often thin
     or cracked at the via edge.
   The clip presses the cell down, and inserting the cell slides it across the mask. One scratch
   or a pinhole in the mask is then a **dead short across the cell**, on the battery side of the
   reverse-polarity FET, so nothing limits it. Without the cell's internal resistance that could
   be ~100+ mA: heating, swelling, and a flat cell inside a closed watch.
   *Fix:* add a B.Cu keep-out under the whole cell (r ≤ 10.5 mm, except pad 2): no pour, tracks or
   vias. Move VBAT and the other B.Cu runs to In1/In2 (In1/In2 can keep the GND pour). If a few
   vias have to stay under the cell, keep them under the minus cap only (r < 7 mm), make them GND
   only, and specify them as filled/capped. Check the MY-2032-16 drawing for any required
   no-copper zone too.
2. **Firmware and board pin maps disagree** (agent/004 2ec9e5f README "Hardware assumptions"
   items 2, 7, 9, 10). The firmware has the buttons on PA6/PA7 and the accelerometer INT on PB6.
   On the board those are charlieplex lines L3, L4 and L6. The board has SW_A = PC2, SW_B = PC3,
   ACC_INT = PC0, I2C pull-ups 4.7 kΩ (not 10 kΩ), and 22 + 10 µF (not 100 µF). *Fix:* 004
   regenerates its pin definitions from PINMAP.md (the board is fine as it is). I've sent 004
   the details. 003, please confirm that PINMAP.md is the source of truth.
3. **The minus pad sits lower than its surroundings** (d). Pad 2 is bare ENIG copper with **no
   paste**, ringed by mask over the GND pour and traces, which are ≈ 10-25 µm higher. With a flat,
   rigid cell this can leave the contact light or intermittent. *Fix:* put F.Paste on pad 2 so
   assembly leaves a solder dome. That's normal practice for PCB-pad coin-cell contacts, and P1's
   keep-out removes most of the higher ring as well. Also confirm the different + tab pads
   (3.0 × 3.5 vs 3.0 × 5.0) against drawing MY-CP-0209; I couldn't get to it.
4. **CPL rotations (f): check the bottom side and the polarised parts in JLCPCB's placement
   preview before paying.** KiCad's bottom-side rotations and JLCPCB's library zero orientations
   often differ by 180° or are mirrored. The parts that matter: SW1/SW2 (the plunger must point
   outwards; a 180° error points it at the cell), U1 pin 1, U2 pin 1, Q1, and one LED from each
   ring (D1 cathode must be on the counter-clockwise side, D61 cathode on the clockwise side).
   BT1's orientation matters if the tab pads really differ. Fix any offsets in export.sh, not by
   hand.
5. **Programming-adapter voltage (minor, safety-related).** With no VDD pad, back-charging can now
   only happen through UPDI's clamp diode. A 3.3 V SerialUPDI adapter with a 470 Ω-1 kΩ resistor
   pushes < 1 mA into a cell below ≈ 2.9 V, which is acceptable for the few seconds programming
   takes. A **5 V** adapter would push several mA. *Fix:* in the build docs, say 3.3 V adapters
   only.
6. **The crystal has SDA running past it.** SDA runs on F.Cu along Y1's top edge (≈ 105.35, 102.0),
   next to XT2. I2C edges can couple into the high-impedance 32 kHz node and add or drop RTC
   ticks during accelerometer reads. *Fix:* route SDA away from Y1 (or put GND copper between
   them) and keep only XT1/XT2 and GND inside Y1's courtyard + 0.5 mm.
7. **The pogo pads are on an arc.** TP1-TP4 are at y = 83.53/83.15/83.15/83.53 (pitch 2.51/2.54/2.51).
   A straight 2.54 mm pogo row is off by up to 0.38 mm on 1.0 mm pads. *Fix:* put them on one
   straight line at exactly 2.54 mm, or make the pads 1.5 mm.
8. **Stock.** ATtiny3217 has 31 and B3U-3100P has 81. Reserve or pre-order them when ordering.
   The ATtiny1617 fallback has 16 KB of flash, so 004 should confirm that the firmware fits.
9. **Mechanical note for the case (D4).** The minute LEDs reach r ≈ 17.8 mm on a 19.0 mm board,
   so the dial or bezel opening must be ≥ 36 mm or the bezel will hide the outer edge of the ring.
   With the case open, the buttons' plungers stick out only 0.4 mm past the board edge, so the
   case pushers need to reach about 0.5 mm in.

## Not verified (no access to datasheets or LCSC pages from here)

LCSC numbers/stock (I took 003's table as given), the XL-1005UYC and LTST-C191KRKT land patterns,
the CM8V-T1A land pattern against KiCad's TXC 2012 footprint, ST's LIS2DH12 land-pattern dimensions,
and the MY-2032-16 drawing.
