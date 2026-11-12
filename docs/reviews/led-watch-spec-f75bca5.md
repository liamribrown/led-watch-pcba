# Review: LED watch SPEC.md (agent/003, f75bca5)

Reviewer: 007, 2026-11-11. Inputs: `projects/led-watch/SPEC.md` (agent/003 f75bca5) and
`projects/led-watch/firmware/REQUIREMENTS.md` (agent/004 8796c39).

**Verdict: approve with changes.** None of the problems below changes 003's recommended answers
to D1–D7, so 000 can decide those now. Items 1–2 are about safety and must be in the schematic.
Items 3–6 fix power or pin errors before the schematic starts. The rest are notes for Phase 2.

Limits of this review: I couldn't get to the Microchip, ST, Energizer or LCSC pages
(403s and timeouts), so I checked the datasheet figures marked "(verify)" below from memory
only. The arithmetic and circuit reasoning are my own and were checked independently.

## What I checked and found correct

- **Power budget arithmetic (§5):** sleep 4.5 µA × 24 h = 0.108 mAh; 5 mA × 50 × 5 s = 0.347 mAh;
  total 0.455 mAh/day; 130–150 mAh ÷ 0.455 = 286–330 days. 20 views/day → 0.247 mAh/day ≈ 1.5 y.
  150 views/day → 1.15 mAh/day ≈ 4 months. Accelerometer share 0.072/0.455 = 16 % (D2's
  "15–20 %"). Without the accelerometer: 0.383 mAh/day ≈ 12 months. All OK.
- **The 130–150 mAh usable from a 225 mAh CR2032 at ~5 mA bursts with long rests** is a reasonable
  room-temperature estimate (verify against the Energizer/Panasonic capacity-vs-drain curves).
- **The LED current formula and 100 Ω per line (§2):** (3.0 − 2.0 − 0.2)/200 = 4.0 mA is right.
  The design limits itself: the cell's internal resistance adds in series with the 200 Ω.
  For example, an old cell at OCV 2.8 V with R_int ≈ 100 Ω gives I ≈ (2.8 − 2.1)/300 ≈ 2.3 mA,
  with VDD sagging to only ≈ 2.57 V. So the LEDs dim gracefully and the MCU never browns out.
  100 Ω is approved. Keep the 0402 footprint so the value can be trimmed after the first
  prototype.
- **Reverse voltage on unlit LEDs:** the LED antiparallel to the lit one sees only −Vf (≈ −2 V),
  well inside the usual −5 V rating. OK.
- **Pin count (§2):** 9 + 2 + 3 + 2 + 1 + 1 = 18 of 22 I/O. The count is right, but see item 5 for
  the actual pin mapping.
- **RTC accuracy table (§4):** ±20 ppm = ±52 s/month. Wrist temperature 30–33 °C:
  −0.034 × (5–8)² = −0.9 to −2.2 ppm. Calibrated total ±3–5 ppm ≈ ±8–13 s/month. Firmware
  add/drop: one 32 kHz tick every N s gives 30.5/N ppm, so N ≥ 31 s for 1 ppm. All OK.
- **Size:** minute-ring pitch 2π·16.5/60 = 1.73 mm (OK for radial 0402). Hour-ring pitch 6.3 mm.
  The inside of the hour ring is ≈ 22 mm across, which is plenty for the MCU, crystal,
  accelerometer, 9 resistors and the decoupling.
- **BOM sum:** ≈ $3.85 against the $4.10 quoted (OK; extended-part fees are in the order total).
- **ATtiny3217 vs STM32L031, CR2032 vs LiPo, no wireless:** I agree with all three
  recommendations.

## Problems

1. **§8 Programming — SAFETY: the programmer can back-charge the CR2032.** The reverse-polarity
   P-FET (gate to GND) conducts in *both* directions once it is on. So 3.3 V on the VDD pogo pad
   with a cell fitted pushes current into a primary lithium cell, which risks leakage or venting.
   "Don't do both at once" in the docs is not enough. *Fix:* never supply power through the
   programming pads. Program from the cell; SerialUPDI needs only GND + UPDI, and a 3.3 V
   adapter into a 3.0 V target is fine through the ~470 Ω series resistor. Label the third pad
   VTREF (sense only) and leave the adapter's 3.3 V unconnected in the jig. For bench power
   without a cell, use a separate pad that only works with the holder empty, or just a supply
   clipped onto the holder pads.
2. **§5/§7 Battery — SAFETY: coin-cell ingestion.** The spec doesn't mention it. A CR2032 in a
   watch must sit in a compartment a child can't open (a screw-down case back or a tool-only
   cover). If this is ever given away or sold, Reese's Law (US) and IEC 62368-1 (EU) also
   require warning labels. *Fix:* add this as a case requirement under D4.
3. **§5 Power — BOD mode is missing from the budget.** "BOD set to ~1.8 V" is right only if the
   BOD is *disabled or sampled* in sleep. If it is continuous, it draws ≈ 20 µA on tinyAVR 1-series
   (verify; sampled at 125 Hz ≈ 0.4 µA, at 1 kHz ≈ 1.2 µA), which would quadruple the sleep current.
   *Fix:* say "BOD disabled in sleep (or sampled 125 Hz), enabled in active mode" in the spec and
   the fuse settings.
4. **§2/§5 — Floating charlieplex nets in sleep.** With all 9 pins high-Z, the 9 LED nets float at
   undefined voltages. The tinyAVR's digital input buffers then draw cross-conduction current,
   which can be µA per pin. The "0.5 µA leakage" line assumes this doesn't happen. *Fix (firmware,
   004):* set `PINnCTRL.ISC = INPUT_DISABLE` on the 9 charlieplex pins (and other unused pins) before
   sleep, or drive all 9 low. Then measure sleep current on the first board.
5. **§2 Pin map — the UART pad and RTC test pad clash with the proposed port use.** On the
   ATtiny3217, TOSC1/TOSC2 are PB3/PB2, and USART0's default TxD/RxD is PB2/PB3 (verify). With the
   crystal fitted, the UART TX therefore has to use the alternate pin PA1. That clashes with
   "charlieplex on PA1–PA7". TWI0 SDA/SCL default to PB1/PB0, so the accelerometer bus is fine.
   §4 and §8 also call for an **RTC/PIT output test pad**, which isn't in the pin table, so the
   total is 19 of 22. *Fix:* put the charlieplex on PA2–PA7 + 3 pins from PB4–PB7/PC0–PC5, UART TX
   on PA1, and the RTC test output via EVOUT or a GPIO toggled in the ISR. Writing across two ports
   is fine for one-LED-at-a-time drive.
6. **§6 Inputs — wake-from-power-down pin choice.** On tinyAVR 1-series only pins 2 and 6 of each
   port are fully asynchronous. Other pins wake from Power-Down only with BOTHEDGES or LEVEL
   sensing (verify). *Fix:* put buttons A/B and LIS2DH12 INT1 on Px2/Px6, or require
   BOTHEDGES/LEVEL sensing in firmware. Agree the full pin map with 004 before the schematic.
7. **§1 Ghosting — the analysis compares the wrong voltage, but the conclusion is safe.** While
   LED A→B is lit, every sneak path (A→X→B, two LEDs in series) sits across the *lit LED*, so it
   sees ≈ Vf ≈ 2.0 V, not V_bat. 2.0 V across two AlInGaP LEDs (≈ 3.0–3.6 V threshold) gives no
   visible glow, even with a fresh 3.3 V cell and red + red. Full V_bat would only reach a sneak
   path if a lit LED were open or unfitted; all 72 positions are populated, so that doesn't happen.
   The real ghosting risk is in firmware during switching. *Fix:* rewrite §1's caveat. The amber
   "mitigation" isn't needed. Firmware sequence: all DIR = 0 → set OUT → set DIR for the 2 new pins.
   An open LED (an assembly defect) would make its own sneak LEDs glow faintly; check for that at
   test.
8. **§5 Bulk capacitor — wrong rationale and oversized.** With one LED always on during a view, the
   cell sees a nearly steady ≈ 5 mA for 5 s. That isn't "low-duty scanning", and no capacitor can
   carry it: 100 µF with a 0.5 V droop holds 50 µC, about 10 ms at 5 mA. The capacitor only smooths
   the ~1 kHz switching edges. A 100 µF MLCC also loses ~50 % at 3 V DC bias and is a large,
   probably extended, part. *Fix:* 10–22 µF 0603/0805 X5R + 100 nF at the MCU, with an optional
   1206 footprint. Correct the text in the power section. Also note that a CR2032's R_int roughly
   doubles at 0 °C, so in winter the time display gets visibly dimmer. Firmware should measure VDD
   *while an LED is lit* when it decides the battery is low.
9. **§4 Crystal — ESR margin with "2012 size".** 2012 32 kHz crystals typically have ESR up to
   80–90 kΩ. The tinyAVR XOSC32K (low-power mode) has a limited ESR/CL envelope (verify the
   datasheet table and AN2648). At 90 kΩ the start-up margin may be below the 3–5× safety factor.
   *Fix:* specify CL ≈ 7 pF, ESR ≤ 70 kΩ (a 3215 part such as the Epson FC-135/Seiko SC-32S class
   is fine, and 3.2 × 1.5 mm fits easily). Fit load-cap footprints sized C = 2·(CL − C_stray).
   Keep the traces under 5 mm with a GND guard and no charlieplex traces under the crystal.
10. **§7 Board — side buttons collide with the minute ring.** The minute LEDs occupy radius
    ≈ 16.0–17.0 mm and the board edge is at 19 mm. A side-push switch body is ≈ 3 mm deep, so on the
    top side it overlaps the ring at 2 and 4 o'clock. *Fix:* put the buttons on the bottom (outside
    the ≈ 12.5 mm-radius cell holder), or shrink the minute ring. Before freezing 38 mm, do a
    routing study of one 30° sector. Each LED needs ≈ 2 vias (≈ 144 total), and a via pad
    (0.45–0.6 mm) plus clearance forces ≈ 0.65 mm arc pitch, so 9 arcs ≈ 6 mm wide on L3. Split the
    nets across L3 and L4 if needed. Use only JLCPCB's standard 0.3/0.45–0.5 mm vias (no extra cost).
11. **§9 Manufacturing — two-sided assembly cost.** JLCPCB's Economic PCBA is single-sided. Bottom-side
    parts (the holder and, per item 10, the buttons) push the order to Standard PCBA, which has
    higher setup fees. *Fix:* keep the bottom side for hand-soldered parts only (the holder and
    buttons have large pads), or budget for Standard. Extended-part fees: about 6–7 extended parts
    (MCU, amber LED, LIS2DH12, crystal, holder, switches, maybe the 0402 amber) × ~$3, so
    $18–21 per order. That roughly fits the $30–40 quoted. Order all 60 + 12 LEDs from one reel/bin.
    Put clear polarity marks for all 72 rotated LEDs on the fab/assembly layer.
12. **§6 Buttons — ESD.** 100 nF on the pin is a good start. Add a 1 kΩ series resistor between the
    switch and the MCU pin (with the 100 nF on the MCU side). Make the optional TVS footprint
    standard (e.g. a 0402/SOD-882 5 V ESD diode). Tie the switches' metal frames/shields to GND. The
    RC with the internal pull-up (≈ 35 kΩ × 100 nF ≈ 3.5 ms) is fine for debounce.
13. **§5 P-FET choice.** Specify a P-FET with R_ds(on) guaranteed at V_GS = −1.8 V or −2.5 V and
    |V_GS(th)| ≤ 1.0 V max (AO3401A or DMG2305UX class), so it stays fully on at a 2.4 V cell. At
    5 mA any of these drops < 1 mV. Optionally add a 100 k gate-to-GND resistor and no gate series
    part. (A CR2032 put in upside down in most holders shorts + to +; the FET mainly guards against
    bench mistakes. It's cheap, so keep it.)
14. **Minor numbers.** 004's light use (10 × 3 s) *with* the accelerometer is 0.042 + 0.108 =
    0.150 mAh/day ≈ 2.5 years, not 3 (3 years assumes no accelerometer). The LIS2DH12 at 10 Hz
    low-power ≈ 3 µA and the ATtiny ≈ 0.7–1 µA with PIT on XOSC32K both match my memory of the
    datasheets (verify, and note the max at 85 °C is much higher). For the LIS2DH12, tie CS to VDD
    and set SA0. Use I2C pull-ups of 10–47 kΩ (no current when idle) and leave them unfitted with
    the accelerometer.

## For Phase 2 / schematic review I'll check

The pin map against firmware, crystal load caps, decoupling at every VDD pin, BOD/fuse
settings, the programming-pad wiring (item 1), LCSC part numbers and stock, and ERC/DRC with kicad-cli.
