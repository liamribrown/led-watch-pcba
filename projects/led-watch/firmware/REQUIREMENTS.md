# LED watch firmware: MCU and LED-drive input for 003 (phase 1)

Author: 004 (Firmware), 2026-11-11. A proposal for 003's hardware spec, not a decision; 000 approves the spec.
Current figures below are from memory of the datasheets and are **orders of magnitude only**: 003/007
please check them against the current datasheets before relying on them.

## 1. Assumed display

- 12 hour LEDs + 60 minute LEDs = **72 LEDs** (seconds can reuse the minute ring).
- Showing the time needs only 2–3 LEDs lit at once (hour, minute, maybe second), so the
  LEDs can be multiplexed with a high per-LED duty cycle.
- Shown for a few seconds after a wake event, then everything off.

## 2. LED drive: recommendation

**Charlieplex 72 LEDs directly from 9 MCU GPIOs** (9 × 8 = 72), one series resistor per line.

| Option | Pins | Extra parts | Standby | Notes |
|---|---|---|---|---|
| **Charlieplex from GPIO** (recommended) | 9 | 9 resistors | ~0 (pins Hi-Z) | Cheapest and lowest power. Firmware cycles through the 2–3 lit LEDs at ≥1 kHz. Needs LEDs with a similar Vf, and a Vf high enough that two in series don't conduct at Vbat (check for ghosting, especially with red LEDs at 3 V). One shorted LED affects others. |
| Row/column matrix (e.g. 8×9) | 17 | resistors, maybe transistors | ~0 | Simpler to reason about, but more pins. |
| I2C LED driver (e.g. ISSI IS31FL3731-class charlieplex driver) | 2 (+SDB) | driver IC | low µA in shutdown (verify), or power-gate it | Constant current, even brightness, less CPU. Adds cost and area. |
| Addressable RGB (WS2812/SK6805-class) | 1 | none | **~0.5–1 mA per LED even when dark** | Avoid unless power-gated by a load switch; too big and power-hungry for a watch. |

Ask: a common LED colour/type for all 72, so brightness and Vf match; a small bulk capacitor near the
MCU if it runs from a coin cell (LED bursts of ~5–10 mA).

## 3. MCU: recommendation

**First choice: Microchip tinyAVR 1/2-series in a 24-pin package (ATtiny3217 / ATtiny3227-class).**

| MCU family | Sleep with RTC (typ., verify) | Why / why not |
|---|---|---|
| **tinyAVR 1/2-series** (ATtiny321x/322x) | ~1 µA power-down with RTC/PIT on 32.768 kHz crystal | Simple, robust, strong GPIO drive (good for charlieplexing), measures its own VDD with no divider, **1-pin UPDI programming** (a USB-serial adapter + Microchip's `pymcuprog`), small toolchain (avr-gcc + avr-libc from Debian). Wide availability. No USB or BLE. |
| STM32L0 / STM32U0 (Cortex-M0+) | ~0.5–1 µA Stop with RTC | Good alternative with more headroom. Toolchain: arm-none-eabi-gcc + CMSIS/LL, OpenOCD; SWD needs 2 pins + reset. Slightly more complex. |
| MSP430FR (FRAM) | ~0.5–1 µA LPM3 with RTC | Excellent power, but less common, and TI tooling is less convenient on Linux. |
| nRF52 (BLE) | ~2–3 µA System ON with RTC | Only if we want phone time sync. Much heavier toolchain (nRF Connect SDK / Zephyr, several GB). Needs an RF layout. |
| ESP32 family, RP2040 | ~10 µA to 100s of µA | **Avoid**: sleep current far too high for a watch battery. |

Battery-life sanity check (coin cell CR2032, ~220 mAh): sleep at 1.5 µA ≈ 0.036 mAh/day; LED bursts at
10 views/day × 3 s × ~8 mA ≈ 0.067 mAh/day. Total ≈ 0.1 mAh/day, about 6 years on paper. Self-discharge and the
cell's poor pulse capability will shorten that, but battery life should still be measured in years. A coin cell's
internal resistance under LED pulses is the main risk; 007 should check it.

## 4. What the firmware needs from the hardware

| Need | Detail | Pins (tinyAVR example) |
|---|---|---|
| **32.768 kHz crystal** | RTC accuracy. The internal low-power oscillator is several % off, which is useless for a watch. | 2 (TOSC1/TOSC2) |
| LEDs | Charlieplex lines, each with a series resistor | 9 |
| Buttons | **2 buttons** (mode/set + advance) on wake-capable pins, to GND, internal pull-ups. One button is possible (long-press menus) but setting the time gets awkward. | 2 |
| Accelerometer (optional) | Wrist-tilt wake: LIS2DH12/LIS3DH-class with motion/tilt interrupt, I2C, ~µA in low-power mode (verify). Interrupt to a wake-capable pin. | 3 (SDA, SCL, INT) |
| Battery voltage | If the MCU runs directly from the battery: measure VDD against the internal reference, no pin needed. If there's a regulator: divider + switching FET (so it draws no current in sleep) to an ADC pin. | 0 (or 1–2) |
| Programming/debug | **UPDI pad + VCC + GND** (3 pads/pogo pins or a Tag-Connect footprint). For STM32: SWDIO, SWCLK, NRST, VCC, GND. | 1 |
| Debug UART (nice to have) | TX test pad, for printf during bring-up | 1 |
| Timers | RTC/PIT for timekeeping and 1 s tick; one TCA/TCB timer for LED multiplex refresh; no other peripherals needed | — |

Total ≈ 18 I/O with accelerometer and UART pad: tight for a 20-pin part, comfortable for the 24-pin (22 I/O) part.

## 5. Firmware behaviour planned for phase 2

- Deep sleep (power-down) with the RTC running; wake on button or tilt; show hour/minute (seconds as an
  option) for a few seconds; back to sleep.
- Time setting: hold the mode button to enter set mode, advance with the other button; the hour LED then the minute LED blinks.
- Battery check on each wake; show a low-battery pattern when low.
- Time-to-LED mapping as a pure C function, unit-tested on the host (gcc) since there is no board yet.
- `build.sh` builds from the command line. Toolchain install waits for 000's approval of the spec.

## 6. Questions for 003

1. Battery: CR2032 coin cell, or a small LiPo with a charger (would need a USB connector/charging pads)?
2. Accelerometer: in or out?
3. LED count and arrangement: 12 + 60, or 12 only (hour LEDs, with minutes shown by blinking)?
4. Any wireless need (BLE time sync)? This decides between tinyAVR/STM32 and nRF52.
