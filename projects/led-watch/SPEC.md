# LED analogue watch: hardware spec (Phase 1)

Owner: 003 (Hardware). Firmware: 004. Review: 007. Approval: 000.
Status: **approved by 000 (D1-D7 as recommended); Phase 2 board done, see "As built" at the end.**
Sections 1-9 are the Phase 1 reasoning; where the board differs, "As built" wins.

A wristwatch PCBA that shows the time like an analogue watch, with LEDs in place of hands.
The LEDs stay dark until a button press or a wrist tilt, then show the time for about 5 s.

Numbers marked *(est.)* are estimates from datasheet typical values or typical distributor
prices. Phase 2 checks them against the actual datasheets and the JLCPCB/LCSC parts library.

## Summary

| Item | Recommendation | Main alternative (why not) |
|---|---|---|
| Display | 60 amber 0402 LEDs on an outer ring (minutes), 12 red 0603 LEDs on an inner ring (hours) | 60-LED ring only, hours shown as a longer "hand" of lit minute LEDs (harder to read at a glance, 3-5 LEDs lit per hand) |
| LED drive | Charlieplex from 9 MCU pins (9 × 8 = 72 LEDs exactly), 9 series resistors | IS31FL3731 I2C matrix driver (more parts, standby current, cost; not needed when only 2-3 LEDs are lit) |
| MCU | ATtiny3217 (tinyAVR 1-series, 32 KB flash, VQFN-24 4 × 4 mm), chosen with 004 | STM32L031K6 (SWD debugging, but a heavier toolchain and a costlier programmer); nRF52 (BLE overkill); ESP32 (far too hungry, see below) |
| Timekeeping | MCU RTC + 32.768 kHz crystal with digital calibration: about ±10 s/month after calibration | RV-3028-C7 RTC chip, about ±3-5 s/month, +$2-3 and one more part |
| Power | CR2032 coin cell, no regulator, reverse-polarity P-FET. About 9-10 months per cell *(est.)* | 3.7 V LiPo + USB-C charging + protection (brighter LEDs, but adds a charger, protection IC, connector and battery-safety risk) |
| Input | 2 side-push buttons + LIS2DH12 accelerometer for wrist-tilt (can be left unfitted) | Buttons only (cheaper, no tilt-to-wake) |
| Board | Round, 38 mm diameter, 4 layers, 1.0 mm FR-4, LEDs + electronics on top, coin-cell holder on the bottom | 2 layers (routing 9 charlieplex nets past 72 LEDs and around a coin cell is very tight) |
| Programming | UPDI from the cell: pogo pads UPDI + GND (+ TX, RTC), no VDD pad; USB-serial adapter + resistor (SerialUPDI) | Tag-Connect footprint (needs a ~$40 cable); STM32 SWD if we switch MCU |
| Manufacturing | JLCPCB 4-layer PCB + SMT assembly, all common LCSC parts. About $4 of parts per board; about $15/board at qty 5 *(est.)* | PCBWay (similar; JLCPCB's parts library is easier to check) |

## 1. Display

**Recommendation:**
- **Minutes:** an outer ring of 60 LEDs, one per minute. 0402 amber (~590 nm), radius ~16.5 mm.
  The pitch at that radius is 1.73 mm, which is comfortable for 0402 placed radially.
- **Hours:** an inner ring of 12 LEDs, 0603 red (~625 nm), radius ~12 mm.
  The larger package and different colour make the hour hand easy to tell apart.
  Firmware can light the hour LED plus the next one dimmed to show "half past".
- **Seconds:** no extra hardware. Firmware can sweep a dim blinking dot on the minute ring
  (an optional mode that uses more power while shown).
- **Brightness:** about 4 mA peak per LED, with one LED on at a time. With 2-3 LEDs scanned,
  each gets 1/2-1/3 duty, which is about 1.3-2 mA average. That's readable indoors and in shade,
  but not in direct sunlight.
  A firmware "boost" (longer duty on one LED, or 1/2 duty) helps outdoors.
  Small high-efficiency AlInGaP parts are bright at these currents.

**Why red/amber and not blue/white/green:** the board runs straight off a coin cell.
The cell gives 3.0 V, falling to about 2.5 V near the end of its life.
Red, orange, amber and yellow (AlInGaP) LEDs have Vf ≈ 1.8-2.1 V, so they keep working down
to an empty cell. InGaN blue, white and true green need 2.8-3.2 V, so they would dim or go out
as the cell drains.
Keeping all 72 LEDs in the same Vf family also matters for charlieplexing. A sneak path is two
LEDs in series *in parallel with the lit LED*, so it only sees the lit LED's ≈ 2.0 V, never the
cell voltage, and it cannot reach the ≈ 3.6-4 V it would need to glow (007 review #7).
The one real cause of ghosting is line capacitance when switching: firmware sets all lines to
input before selecting the next LED.
004 asked for one LED type for all 72. Two AlInGaP types with similar Vf meet the electrical
need, and firmware can trim per-ring duty to match brightness. D5 lets 000 choose a single
colour instead.

**Alternative: one 60-LED ring, hours as a different brightness or blink pattern.**
Not chosen, because an analogue face is read by hand *length and position*. Two rings
(or two colours) are what make it readable at a glance.

## 2. LED drive

**Recommendation: charlieplexing directly from the MCU.**
9 GPIOs drive n(n-1) = 9 × 8 = **72 LEDs**, exactly 60 + 12. 004 reached the same design independently. There is one series resistor per
line (9 resistors), so every LED sees two of them.
Firmware drives one LED at a time from a timer interrupt: one pin high, one pin low, the other
7 pins high-impedance. It cycles through the 2-3 lit LEDs at ≥ 200 Hz (004 plans ~1 kHz).

- Current per LED: I = (V_bat − Vf − V_gpio) / (2R). With 100 Ω, a fresh cell gives
  (3.0 − 2.0 − 0.2) / 200 ≈ 4 mA. A cell at 2.6 V gives about 2 mA.
  Firmware measures V_bat against the internal reference, with no extra pin, and lengthens the
  duty to keep brightness even.
- Peak GPIO current of 4 mA is well within the tinyAVR per-pin rating (pins drop only ~0.1 V at this current).
- Extra parts: 9 resistors. Standby current: zero (all pins high-Z).

**MCU pin count** (ATtiny3217, VQFN-24, 22 I/Os including UPDI):

| Function | Pins |
|---|---|
| Charlieplex lines | 9 (mostly one port, e.g. PA1-PA7 + 2 more, for fast writes through the VPORT registers) |
| Buttons (EXTI wake) | 2 |
| Accelerometer I2C (SCL, SDA) + INT | 3 |
| 32.768 kHz crystal (TOSC1/TOSC2) | 2 |
| UPDI (programming, PA0) | 1 |
| Battery voltage | 0 (VDD = battery, measured against the internal reference) |
| UART TX test pad (004: nice to have) | 1 |
| **Total** | **18** |
| Spare | 4 |

**Alternatives:**
- *IS31FL3731 (I2C, 144-LED charlieplex driver):* constant current, 8-bit PWM per LED, and very
  little firmware. Not chosen because it adds a 28-pin IC, about $1.50 and standby current
  unless it is power-gated. It saves nothing on a display that lights only 2-3 LEDs.
  It is the right choice if we later want many LEDs lit at once (e.g. animations, a filled arc).
- *Shift registers (e.g. 74HC595 × 9) or a 9 × 8 matrix:* more parts, more board area and more
  standby current, with no benefit here.

## 3. MCU

**Recommendation (joint with 004): Microchip ATtiny3217** (tinyAVR 1-series AVR, up to 20 MHz,
32 KB flash, 2 KB RAM, 22 I/Os, VQFN-24 4 × 4 mm).
004's full reasoning is in `projects/led-watch/firmware/REQUIREMENTS.md` on agent/004 (commit 8796c39).

- **Low power:** about 1 µA asleep with the RTC running on a 32.768 kHz crystal *(est.; to
  confirm from the datasheet)*. It wakes on RTC/PIT, buttons or the accelerometer interrupt.
  It runs at 1-2 MHz (prescaled) while the LEDs are on, at well under 1 mA.
- **Runs straight from the cell** (1.8-5.5 V; ≤ 5 MHz at 1.8 V), so no regulator is needed.
  It measures its own VDD against the internal reference.
- **Strong GPIO drive,** which suits charlieplexing.
- **1-pin UPDI programming** with a USB-serial adapter and a resistor (§8).
- **Small toolchain from Debian:** `gcc-avr`, `avr-libc`, `avrdude` (SerialUPDI). 004 plans
  plain C with host-side unit tests.
- It has 22 I/Os and we use 18, leaving 4 spare.
- **Pin-compatible fallback:** ATtiny3227 (2-series, 3 KB RAM) if LCSC stock is better.
  The 24-pin 1-series and 2-series pinouts must be checked against each other in Phase 2
  before treating them as drop-in.

**I first proposed STM32L031K6U6** (Cortex-M0+, ≈ 0.9 µA Stop + RTC, RTC smooth calibration,
SWD). It is the main alternative.
We picked the ATtiny because sleep current is about the same and this firmware is small (an
RTC, a timer ISR and two buttons). The tinyAVR has:
- a simpler toolchain and programmer (no ST-Link/OpenOCD),
- 3 programming pads instead of 5,
- the firmware owner's preference.

What we give up is hardware debugging (breakpoints over SWD). The UART pad and host unit tests
cover that for firmware this size.

**Why not an ESP32:**
- Active current with Wi-Fi/BLE is 80-350 mA in bursts. A coin cell can't supply that, and a
  small LiPo would last days, not months.
- Deep sleep is ≈ 5-10 µA, about 5-10 times the tinyAVR with its RTC.
- The internal 150 kHz RTC oscillator drifts by percent, unless we add a 32 kHz crystal anyway.
- The module (≈ 18 × 25 mm with antenna) doesn't fit well inside a 38 mm round board with
  LED rings, and its antenna would sit in a metal case.
- Wi-Fi/NTP time sync is the one real benefit. For a watch, setting the time with buttons
  once or twice a year is fine.
- RP2040 is out for the same sleep-current reason.

**Other alternatives:**
- *STM32U031:* the newer successor to the L0, with lower power. Same trade-off as the STM32L031.
- *MSP430FR:* excellent power, but TI tooling is less convenient on Linux.
- *nRF52810/832:* BLE time sync from a phone is nice, but it costs more, has a heavier toolchain
  (Zephyr), needs RF layout and matching, and the antenna is poor in a metal case.
  It's only worth it if 000 wants BLE (D7).

## 4. Timekeeping

**Recommendation: the MCU's RTC + a 32.768 kHz crystal (2012 size, ±20 ppm, low CL to suit
the tinyAVR's low-power XOSC32K), with drift correction in firmware.**

| | Uncalibrated | Calibrated |
|---|---|---|
| Crystal tolerance at 25 °C | ±20 ppm → ±52 s/month | trimmed to ≈ ±2 ppm |
| Temperature (wrist ≈ 30-33 °C; tuning-fork curve −0.034 ppm/°C²) | −1 to −2 ppm | same, can be pre-compensated |
| Ageing | ±3 ppm/year | ±3 ppm/year |
| **Typical total** | **±20-60 s/month** | **±5-15 s/month** |

Calibration works in one of two ways:
- Measure the RTC output (512 Hz or 1 Hz on a test pad) once with a frequency counter.
- Or let firmware learn it: when the user corrects the time, firmware updates a stored ppm
  correction.

Firmware applies the correction by adding or dropping one RTC tick every N seconds, at
better than 1 ppm resolution. (The 2-series ATtiny3227 may have a hardware calibration
register; to check in Phase 2.)

**Alternative: Micro Crystal RV-3028-C7** (I2C RTC, factory-calibrated ±1 ppm at 25 °C,
≈ 45 nA). That gives ≈ ±3-5 s/month without calibration work.
Not chosen by default because it adds about $2-3 and one more part, and a calibrated MCU RTC is
close enough for this watch.
It's a clean upgrade if 000 wants "set once a year" accuracy (decision D3). It would share the
accelerometer's I2C bus, so it needs no extra pins.

## 5. Power

**Recommendation: one CR2032 lithium coin cell, VDD = battery directly (no regulator), with a
P-MOSFET for reverse-polarity protection and 22 µF + 100 nF of ceramic decoupling (plus 100 nF at the accelerometer).**
While the time is shown the cell supplies a steady ≈ 5 mA for 5 s; a capacitor cannot carry that
(100 µF would last ≈ 10 ms), so bulk capacitance only smooths the scan edges (007 review #8).

### Power budget *(est.)*

| State | Current | Time per day | Charge per day |
|---|---|---|---|
| MCU sleep + RTC on 32 kHz crystal | 1 µA | 24 h | 0.024 mAh |
| LIS2DH12, low-power 10 Hz wake-on-motion | 3 µA | 24 h | 0.072 mAh |
| P-FET, button pull-ups, leakage | 0.5 µA | 24 h | 0.012 mAh |
| **Sleep subtotal** | **≈ 4.5 µA** | | **0.108 mAh** |
| Time shown: LEDs ≈ 4 mA (one at a time) + MCU ≈ 1 mA | ≈ 5 mA | 50 views × 5 s | 0.347 mAh |
| **Total** | | | **≈ 0.45 mAh/day** |

- **CR2032:** nominally 225 mAh, but it delivers less at mA pulses. Assume about 130-150 mAh
  usable, which gives **≈ 290-330 days (9-11 months)** at 50 views a day.
- 20 views a day → about 1.5 years. 150 views a day (or many false tilt wake-ups) → about 4 months.
- 004's lighter use case (10 views × 3 s a day) with the accelerometer gives ≈ 0.150 mAh/day,
  about 2.5 years.
  The 50-view figure above is deliberately conservative.
- Leaving the accelerometer unfitted (buttons only) cuts sleep current to ≈ 1.5 µA, and the
  battery life becomes ~10-12 months, limited by viewing.
- The cell's internal resistance is in series with the LED resistors, so an old or cold cell
  dims the LEDs gently rather than browning out the MCU. Firmware still refuses to light the LEDs
  below ≈ 2.4 V. BOD must be off (or sampled at 125 Hz) in sleep: continuous BOD costs ≈ 20 µA.
- The 9 charlieplex lines float in sleep: firmware sets INPUT_DISABLE on them (007 review #4).
  Measure sleep current on the first board.

**Alternative: 3.7 V LiPo (≈ 80-120 mAh) + USB-C charging.** Not chosen, because it needs:
- a charger IC (e.g. TP4054/MCP73831),
- a protection IC + dual FET (DW01A + FS8205, or a protected cell),
- a low-Iq 3.0 V LDO,
- a USB-C receptacle (about 3.2 mm tall on a board edge, and a case opening).

The protection and LDO alone draw ≈ 3-5 µA. There is also a lithium-battery safety review, and
shipping a watch with a LiPo is harder.
What it gains: brighter LEDs, any LED colour, and recharging instead of replacing a cell every
~9 months. Worth revisiting if 000 wants white/blue LEDs or a brighter, always-on mode
(decision D1).

## 6. Input

**Recommendation:**
- **2 side-push tactile switches** on the board edge (e.g. 4 × 3 mm right-angle SMD, ≈ 1.5 mm
  plunger travel) where a watch case's crown or pushers can reach them:
  - **A (top right):** show the time.
  - **B (bottom right):** with A, set the time. Hold A + B for 2 s to enter set mode. In set mode,
    A steps the hour and B steps the minute, and it saves after 5 s idle.
  - Internal pull-ups, active low, EXTI wake. Each button gets a 100 nF debounce/ESD capacitor.
    A TVS footprint is optional if the case pushers are metal.
- **LIS2DH12 accelerometer** (2 × 2 mm LGA-12, I2C, INT1 to an EXTI pin) for wrist-tilt-to-wake.
  Firmware uses its low-power wake-on-motion mode, then checks orientation (face up, roughly
  level) before lighting.
  It's on the board but can be left unfitted (D2): a buttons-only build still works.
  *Alternative:* LIS2DW12 (lower power, about 1 µA in its lowest mode, but less often in stock).
  We'll check stock in Phase 2.

## 7. Board

**Recommendation: round, 38 mm diameter, 4-layer FR-4, 1.0 mm thick, ENIG finish.**

- **Top:** the 60 + 12 LED rings, the MCU, crystal, accelerometer, charlieplex resistors and
  decoupling all sit inside the hour ring (an 18-20 mm diameter area in the middle).
  A printed dial or diffuser can cover the centre.
- **Bottom:** the CR2032 SMD holder (≈ 20 mm footprint), UPDI programming pads, test pads.
  The buttons go on the edge, on top or bottom depending on the case.
- **Layers:** L1 LEDs + parts, L2 GND, L3 the 9 charlieplex buses as concentric arcs,
  L4 battery holder and VDD. With 2 layers, the 9 nets would have to circle the board under the
  coin cell, which is very tight. 4-layer at JLCPCB is now only a few dollars more.
- **Thickness:** 1.0 mm (0.8 mm is possible if the case is very thin).
- **Size depends on the case.** 36-40 mm suits most 40-44 mm men's watch cases. If 000 has a
  target case (D4), the diameter, button positions and mounting holes come from it.

## 8. Programming and debug

**Recommendation: program from the cell over UPDI. Pogo pads on the bottom at 2.54 mm pitch:
UPDI, GND, TX, RTC. There is deliberately no VDD pad (007 review #1, safety).**

- **Programmer:** any 3.3 V USB-serial adapter (CH340/CP2102/FT232, ≈ $5) plus one ~470 Ω
  resistor between TX and RX (Microchip's "SerialUPDI").
- **Software:** `avrdude -c serialupdi` (Debian package) or Microchip's `pymcuprog`.
- **Jig:** a 3-pin pogo clip or a small 3D-printed jig, about $5-10. The ATtiny pads are also
  hand-solderable.
- **Debug:** a UART TX test pad for printf logs, and an RTC/PIT output test pad for measuring
  calibration.
- **Powering:** always from the coin cell. Q1 conducts in both directions once it is on, so 3.3 V
  fed into VDD would charge a fitted CR2032 (a lithium primary cell must never be charged).
  SerialUPDI only needs UPDI + GND; the adapter's 3.3 V signals are fine against a 2.5-3.2 V cell.

*Alternative:* a Tag-Connect TC2030-NL footprint (a cleaner fixture, but a ~$40 cable).
No USB: it would cost height, a case opening and current, and the ATtiny has none.

## 9. Manufacturing and rough BOM

**Target:** JLCPCB 4-layer PCB + SMT assembly. All parts from the LCSC catalogue, preferring
"basic" parts (no per-part setup fee) where possible.
**Double-sided assembly:** the coin-cell holder is on the bottom. JLCPCB charges a second-side
setup for this, or the holder (the only bottom part) can be hand-soldered.

| Part | Qty | Unit *(est.)* | Notes |
|---|---|---|---|
| ATtiny3217-MNR | 1 | $1.10 | extended part; ATtiny3227 as fallback |
| LED 0402 amber | 60 | $0.015 | check Vf/brightness bin |
| LED 0603 red | 12 | $0.015 | basic part |
| LIS2DH12TR | 1 | $0.80 | optional (D2) |
| 32.768 kHz crystal 2012 | 1 | $0.20 | |
| CR2032 SMD holder | 1 | $0.30 | |
| Side-push tactile switch | 2 | $0.10 | |
| P-MOSFET SOT-23 (reverse polarity) | 1 | $0.05 | |
| Resistors/capacitors 0402 | ~20 | $0.005 | basic parts |
| **Parts per board** | | **≈ $4.10** | |

**Order cost *(est.)*:**
- 5 assembled boards: PCB ≈ $10-20, assembly setup + extended-part fees ≈ $30-40, parts
  ≈ $25. That's **≈ $65-85 total, ≈ $15/board**.
- 50 boards: ≈ $8/board.
- The cell is bought separately.

## 10. Decisions from 000 (all approved as recommended, 2026-11-11)

| # | Decision | Recommended answer |
|---|---|---|
| D1 | **Power:** CR2032 coin cell (red/amber LEDs, ~9-10 months per cell) or LiPo + USB-C charging (any colour, brighter, recharge every few months, more parts and battery-safety work)? | **CR2032** |
| D2 | **Wrist-tilt:** fit the LIS2DH12 accelerometer (≈ +$0.80 and ≈ 3 µA, about 15-20% of battery life, plus whatever false wake-ups add) or buttons only? | **Fit it**, with a footprint that can be left unfitted |
| D3 | **Accuracy:** calibrated MCU RTC (≈ ±5-15 s/month) or add an RV-3028 RTC chip (≈ ±3-5 s/month, +$2-3)? | **MCU RTC** |
| D4 | **Case:** is there a target watch case (diameter, crown/pusher positions, depth)? If not, design for a 38 mm round board and pick a case to fit later. | **No case yet → 38 mm** |
| D5 | **Colours:** amber minutes + red hours? (With a coin cell, only red/orange/amber/yellow work well.) | **Amber + red** |
| D6 | **MCU:** ATtiny3217 (004's and my pick: simple, UPDI, Debian toolchain) or STM32L031 (SWD debugging, ST-Link needed)? | **ATtiny3217** |
| D7 | **Wireless:** no BLE/Wi-Fi (time set by buttons)? BLE phone sync would mean an nRF52, more cost and RF layout. | **No wireless** |

## As built (Phase 2, board rev A)

Files: `led-watch.kicad_sch`, `led-watch.kicad_pcb` (generated by `tools/generate.py`), firmware
pin map `PINMAP.md` (generated), exports with `./export.sh`. ERC and DRC (with schematic parity)
report 0 errors and 0 warnings.

### Board

- 38 mm round, 4 layers, 1.0 mm. Top: 60 minute LEDs at r = 17.3 mm, 12 hour LEDs at r = 9.6 mm,
  all electronics inside r < 8.4 mm. Bottom: CR2032 clip, two side buttons (2 and 4 o'clock),
  pogo pads at 12 o'clock, button resistors and ESD footprints.
- Charlieplex wiring: LEDs share anodes in blocks of 8 (a copper arc joins each block's anodes),
  so every LED needs one via. The 9 lines are concentric rings on In2; spokes on In1 bring them to
  the 100 Ω resistors next to the MCU. In1, In2 and B.Cu are GND pours.
- The CR2032 minus contact is a 5.5 mm bare-copper pad under the cell; the clip's two tabs are + .
- Polarity dots on F.Silkscreen at every LED cathode. Part silkscreen is moved to Fab (no room);
  JLCPCB places from the CPL file.

### Changes from sections 1-9

| What | Spec said | As built | Why |
|---|---|---|---|
| Buttons | Alps side switch 4.5 × 3.4 mm | Omron B3U-3100P 3.0 × 2.5 mm, bottom | the Alps pegs' holes would hit minute LEDs; B3U has none |
| Button circuit | pull-up + 100 nF | + 1 kΩ series R, DNP ESD diode footprint, switch frame to GND | 007 #12 |
| Programming pads | UPDI, VDD, GND | UPDI, GND, TX, RTC (no VDD) | 007 #1 safety: no way to back-charge the cell |
| Bulk caps | ≈ 100 µF | 22 µF + 100 nF (the 10 µF was dropped in the board-review round) | 007 #8 |
| Crystal | 2012, ±20 ppm | Micro Crystal CM8V-T1A, 7 pF, 70 kΩ, 2 × 6.8 pF C0G | 007 #9: ESR inside XOSC32K's 80 kΩ limit at CL 7.5 pF (datasheet table 37-14) |
| Pin map | 9 lines on one port | L0-L8 = PA3-PA7, PB7-PB4; RTC test pad on PA2 (EVOUT0) | routing; 004's request for an RTC pad |
| LIS2DH12 SA0 | "strap" | tied high (address 0x19) | internal pull-up: tied low it would draw ≈ 100 µA |

### Verified from datasheets (2026-11-11)

- ATtiny3217: Standby with RTC on XOSC32K **0.69 µA** typ at 3 V; Power-down 0.1 µA; XOSC32K CL
  7.5-12.5 pF, ESR ≤ 80 kΩ at 7.5 pF, 5.5 pF per pin; pin functions from the I/O multiplexing table.
  The 1-series RTC has no hardware calibration register: drift correction is in firmware.
- LIS2DH12: low-power mode **2 µA at 1 Hz, 3 µA at 10 Hz**, 0.5 µA power-down; pinout table 2.

### 007 spec review: how each item was handled

| # | Item | Done |
|---|---|---|
| 1 | VDD pad back-charges the cell | VDD pad removed; program from the cell |
| 2 | Child-resistant cell compartment | **Case requirement**: the cell must only be reachable with a tool (screw-down back); add coin-cell warnings if the watch is given away |
| 3 | BOD current | firmware rule in PINMAP.md and §5 |
| 4 | Floating lines in sleep | firmware rule (INPUT_DISABLE); measure sleep current on board 1 |
| 5 | TX/charlieplex pin clash | TX on PA1, lines on PA3-PA7 + PB4-PB7 |
| 6 | Async pins | SW_A on PC2 (async); SW_B and ACC_INT use BOTHEDGES/LEVEL |
| 7 | Ghosting text | §1 rewritten; firmware sets all DIR = input before switching |
| 8 | Bulk cap reasoning | §5 rewritten; 22 µF + 100 nF |
| 9 | Crystal ESR | 70 kΩ, 7 pF part chosen, load caps fitted |
| 10 | Switch placement + routing study | switches on the bottom; full board routed, DRC clean |
| 11 | Single-sided PCBA, polarity | bottom has 5 parts (BT1, SW1, SW2, R12, R13): use Standard PCBA or hand-solder them; cathode dots added |
| 12 | Button protection | 1 kΩ + 100 nF + DNP ESD footprint |
| 13 | P-FET spec | AO3401A: Vgs(th) −0.5 to −1.3 V, 85 mΩ at −2.5 V (from memory: 007 please verify) |
| 14 | Battery figure, I2C pull-ups | §5 corrected; pull-ups are 4.7 kΩ (idle-high bus, no static current) and are fitted only with U2 |

### BOM (LCSC stock checked on lcsc.com, 2026-11-11)

| Refs | Part | LCSC | Stock | Notes |
|---|---|---|---|---|
| U1 | ATtiny3217-MNR | C614177 | **31** | low stock; fallback ATtiny1617-MNR C614176 (117), same package and pinout, 16 KB |
| U2 | LIS2DH12TR | C110926 | 6,927 | |
| Y1 | CM8V-T1A 32.768 kHz 7 pF | C5136974 | 38,895 | |
| C5, C6 | 6.8 pF C0G 0402 | C1576 | 115,100 | |
| Q1 | AO3401A | C15127 | 1,167,545 | basic part |
| BT1 | MY-2032-16 clip | C2902340 | 40,655 | bottom |
| SW1, SW2 | Omron B3U-3100P | C6748648 | **81** | bottom; enough for ~40 boards |
| D1-D60 | XL-1005UYC yellow 590 nm 0402 | C25503856 | 175,500 | order one reel / one bin |
| D61-D72 | LTST-C191KRKT red 639 nm 0603 | C125099 | 382,500 | |
| R1-R9 | 100 Ω 0402 | C25076 | 6,628,800 | |
| R10, R11 | 4.7 kΩ 0402 | C25900 | 7,522,300 | |
| R12, R13 | 1 kΩ 0402 | C11702 | 20,680,200 | bottom |
| C1, C4, C7, C8 | 100 nF 0402 | C1525 | 826,600 | |
| C3 | 22 µF 0805 | C45783 | 409,200 | |
| D73, D74 | ESD diode 0402 | — | — | not fitted |

**Actual JLCPCB quote (2026-11-12): $231.08 for 10 boards, Standard PCBA, both sides, before shipping** (≈ $23 per board).
Estimate before the quote: about $4.5 of parts per board. JLCPCB fees: about 7 extended parts × $3 per order, and a second-side
setup for the 5 bottom parts (or solder those by hand).

### 007 board review (9cdeb82): fixes in rev A

| # | Finding | Fix |
|---|---|---|
| 1 | **[SAFETY]** copper on B.Cu under the CR2032, separated from the cell only by mask | B.Cu keep-out rule area r ≤ 10.5 mm: no tracks, no pour (only the minus pad 2 and the clip's + tabs, which are at the matching cell potentials). VBAT and VDD have **no vias under the cell**: VDD runs on F.Cu only, along a VDD "spine" arc at r = 8.15 mm outside all centre parts; Q1 sits in a gap in the spine at 11:30 and VBAT comes in from outside the cell along a free sector boundary (345°) to Q1's drain, then on B.Cu outside the keep-out to the clip tabs. GND vias under the cell only below the minus cap (r < 6.7 mm, same potential as the cap). The remaining vias under the cell are current-limited signals (LED lines through 100 Ω / MCU pins, I2C, buttons through 1 kΩ); they are tented and keep no copper ring on B.Cu. Order note: ask for plugged (filled) vias. |
| 2 | Firmware pin map | 004's firmware (agent/004 81f15c1) now matches: board.h pins and all 72 LED-table entries checked against PINMAP.md. **PINMAP.md is the source of truth.** |
| 3 | Minus pad lower than its surroundings | four Ø1 mm paste dots on pad 2 leave solder domes; the keep-out removes the masked copper around it. Tab pads 3.0 × 3.5 and 3.0 × 5.0 mm are as drawn in MY-CP-0209 ("PCB Layout Diagram, Top View": 3.50 left, 5.00 right, 25.90 overall). |
| 4 | CPL rotations | `ROT_FIX` table in export.sh; fill it in from JLCPCB's placement preview before paying (parts listed there). |
| 5 | Programming adapter | **3.3 V SerialUPDI adapters only.** A 5 V adapter pushes mA into the cell through the UPDI clamp diode. |
| 6 | SDA beside the crystal | F.Cu inside Y1's courtyard + 0.5 mm is reserved for XT1/XT2/GND; SDA and SCL now drop to the inner layers at the accelerometer. |
| 7 | Pogo pads on an arc | TP1-TP4 on one straight line, 2.54 mm pitch. |
| 8 | Stock | reserve ATtiny3217 (31) and B3U-3100P (81) when ordering. The ATtiny1617 fallback has 16 KB flash: 004 to confirm the firmware fits. |
| 9 | Case | dial/bezel opening ≥ 36 mm (minute LEDs reach r 17.8 mm); pushers must reach ≈ 0.5 mm inside the board edge at 2 and 4 o'clock (the plunger outline ends ≈ 0.4 mm past the edge, r 19.38 mm). Cell behind a tool-only back (spec review #2). |

Layout changes this round: the LIS2DH12 is rotated 180° so SCL/SDA/CS/SA0 face outwards; SCL and
SDA drop to the inner layers at its pads, and CS (no internal pull-up) and SA0 take VDD on F.Cu from the
pull-up resistors beside them (a VDD via next to them would be under the cell). Y1 is vertical so XT1
and XT2 do not cross. `tools/check_cell.py` checks all of the cell rules and `export.sh` stops if it fails.
007 approved the board at 5a2effa (review `agents/007/reviews/led-watch-board-5a2effa.md` on agent/007).
Follow-ups done since: no via within 0.85 mm of a pad-2 paste dot (N1), check_cell.py measures whole
track segments (N3). **Open for the order:** fill `ROT_FIX` from JLCPCB's placement preview (#4), and
order **plugged/filled vias for ALL vias** (N2 and 007's check of review B4: ~30 signal vias sit under
the minus cap at r 3.2-6.6 mm and some under the + rim at r 8.6-10 mm; a mask defect there would short a
signal to the cell, a function failure rather than a cell short). Rev B could move the rim vias inside r 8 mm. The ATtiny1617 fallback is fine: firmware is ≈ 3.8 KB flash, 65 B RAM (004).
