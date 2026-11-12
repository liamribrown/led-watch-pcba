# LED watch firmware (ATtiny3217)

Owner: 004. Hardware spec: `projects/led-watch/SPEC.md` (003, approved by 000).
Plain C, no Arduino core, no vendor libraries. Not yet run on hardware: there is no board yet.

## What it does

- **Asleep:** power-down mode. The RTC's periodic interrupt (PIT) wakes the CPU once a second
  from the 32.768 kHz crystal to count time, then it sleeps again. All LED lines float with input
  buffers off.
- **Wake:** button A, or a wrist tilt (LIS2DH12 motion interrupt, then a "face up and level" check).
- **Show:** hour LED (red ring) + minute LED (amber ring) + a dim seconds dot, for 5 s
  (re-armed by another press or tilt). LEDs are charlieplexed, one at a time, 4 kHz tick / 250 Hz frame.
  On-time per LED grows from 4/16 to 7/16 of the frame as the cell drops from 3.0 V to 2.6 V, to keep brightness even.
- **Battery:** VDD is measured against the internal 1.1 V reference on every wake. Below 2.4 V the time
  isn't shown, only a short dim blink at 12 o'clock.
- **Set the time:** hold A + B for 2 s. Both hands blink. A steps the hour, B steps the minute
  (hold B to auto-repeat), and stepping the minute zeroes the seconds. Saved after 5 s with no press.
  After a battery change the watch starts in set mode (60 s timeout) at 12:00.
- **Calibration:** a correction in 0.1 ppm steps, stored in the user row (survives re-flashing), applied
  by adding or dropping one second when the accumulated error reaches a second. See `set-calibration.sh`.
- **No LIS2DH12 fitted:** detected at start-up (no WHO_AM_I answer). Tilt is then off and its pin disabled.

## Files

| File | Role | Host-tested |
|---|---|---|
| `src/led_map.c` | LED numbering and the charlieplex (anode, cathode) table | yes |
| `src/clockface.c` | time → one 16-tick scan frame | yes |
| `src/timekeep.c` | 12-hour clock, calibration accumulator, setting | yes |
| `src/battery.c` | ADC → mV, duty compensation | yes |
| `src/ui.c` | buttons/tilt state machine (debounce, show, set mode, timeouts) | yes |
| `src/tilt.c` | "face up" test on an accelerometer sample | yes |
| `src/main.c` | pins, scan ISR, PIT, ADC, sleep, main loop, fuses | no (needs hardware) |
| `src/twi.c`, `src/lis2dh12.c` | I2C master and accelerometer set-up | no (needs hardware) |
| `src/board.h`, `src/led_table.h` | pin map; generated LED table (`tools/gen_led_table.py`) | table checked against PINMAP.md |
| `test/test_main.c` | host unit tests (~124 000 checks, including all 72 LEDs and every minute of 12 h) | — |

## Build, test, flash

```bash
./build.sh            # host tests (gcc with ASan/UBSan), then firmware → build/led-watch.hex
./build.sh test       # tests only
./build.sh firmware   # firmware only
./flash.sh /dev/ttyUSB0          # only with 000's OK; needs dialout access (ask 000)
./set-calibration.sh +12.3       # store a crystal correction (see the script for how to measure)
```

Firmware size: 3.8 KB of 32 KB flash (.text 3750 + .rodata 72 for the LED table, .data 0), 65 B of 2 KB RAM.
It also fits the pin-compatible ATtiny1617 (16 KB flash, 2 KB RAM): `MCU=attiny1617 ./build.sh firmware` gives the
same sizes. `flash.sh` and `set-calibration.sh` use avrdude part `t3217`; use `t1617` for that chip.
Fuses: only BODCFG changes (0x04: BOD 1.8 V while awake, off in sleep). The rest stay at factory
defaults, and `flash.sh` never writes SYSCFG0 (that fuse keeps PA0 as UPDI).

## Toolchain (Debian 13 packages, installed 2026-11-11)

```bash
sudo apt-get install gcc-avr avr-libc binutils-avr avrdude
```

| Package | Version | Notes |
|---|---|---|
| gcc-avr | 14.2.0 | supports `-mmcu=attiny3217` and `attiny3227` natively, no Microchip pack needed |
| avr-libc | 2.2.1 | has `iotn3217.h` / `iotn3227.h` |
| binutils-avr | 2.43.50 | |
| avrdude | 7.1 | `-c serialupdi`; parts `t3217`, `t3227` |
| gcc (host) | 14.2.0 | for the unit tests |

Programmer: any 3.3 V USB-serial adapter with a ~470 Ω resistor from TX to RX, RX to the UPDI pad
(Microchip "SerialUPDI"). Not tested yet.

## Pin map

Source of truth: the board's generated `projects/led-watch/PINMAP.md` (003). `src/board.h` mirrors it, and
`src/led_table.h` (the 72-LED anode/cathode table) is **generated from it** by `tools/gen_led_table.py`;
`./build.sh` re-checks the table against `../PINMAP.md` whenever that file is present.

| Pin | Use | Pin | Use | Pin | Use |
|---|---|---|---|---|---|
| PA0 | UPDI | PB0 | I2C SCL (4.7 k pull-up) | PC0 | LIS2DH12 INT1 (push-pull, active low) |
| PA1 | UART TX test pad (USART0 alternate) | PB1 | I2C SDA (4.7 k pull-up) | PC1 | spare |
| PA2 | RTC test pad (toggles each second in the `CAL_OUT` build) | PB2 | TOSC2 | PC2 | button A |
| PA3–PA7 | LED lines L0–L4 | PB3 | TOSC1 | PC3 | button B |
| PB7, PB6, PB5, PB4 | LED lines L5, L6, L7, L8 | | | PC4, PC5 | spare |

LIS2DH12: top side (+Z out of the dial), I2C address 0x19 (SA0 high). There is no VDD programming pad:
program from the cell with UPDI + GND.

**Charlieplex wiring:** the per-LED (anode line, cathode line) pairs come from the board, not from a formula.
LED numbers: 0–59 minutes clockwise from 12, 60–71 hours from 12.

## Sleep and wake design

- BOD is off in sleep (fuse `BODCFG` = 0x04). All unused pins, and all LED lines, have their input buffer disabled.
  The TWI pins (PB0/PB1) are left alone until the accelerometer has answered, and disabled only if it didn't.
- Wake inputs (A and INT1) use **low-level** sensing, armed only for pins that are currently high
  (`wake_arm()` in `main.c`; B is only read while awake, and set mode starts from A). That doesn't rely on edge detection in power-down, which only some pins support.
  The cost: a button that is *held* when the watch goes to sleep (stuck switch, pressed against a sleeve) is not
  armed, so it can't wake the chip in a loop; it's re-armed at the next 1 s RTC wake after release. So a
  stuck button costs nothing in sleep current, and a press within about 1 s of releasing it may be missed.
- A latched INT1 left low (motion during start-up, or one failed I2C read) is retried at every wake: the sensor
  is read, which releases the latch.
- LED scan order (007's rule): all lines driven low (drain) → all lines to input → drive the next pair.

## Hardware assumptions for 007 to check

1. VQFN-24 pin functions as in `PINMAP.md`; TWI0 default pins are PB0/PB1; USART0 alternate TX is PA1.
2. **Power-down wake by LOW level or BOTHEDGES works on every PORT pin; RISING/FALLING-only needs a fully
   asynchronous pin** (PC2 is one, PC0 and PC3 are not, per `PINMAP.md`). Source: Microchip PORT chapter, section
   16.3.3.1 "Asynchronous Sensing Pin Properties" (found by 002; a general page, not the ATtiny3217 datasheet
   itself, so the I/O multiplexing table still needs a look). This firmware uses level sensing on A and INT1.
   A latched INT1 stays low until read, which meets the "held until the clock restarts" condition.
3. The RTC PIT keeps running in power-down from XOSC32K (1k start-up), and the crystal's load capacitance suits
   the low-power XOSC32K (the board uses a 7 pF crystal).
4. Sleep current about 1 µA for the MCU with the PIT on, plus the LIS2DH12. Waking once a second adds well
   under 0.1 µA on average. *From memory.*
5. LED drive: one LED at a time, about 4 mA peak with 100 Ω per line.
6. Battery measurement: VDD = 1.1 V × 1023 / ADC reading; the 1.1 V reference tolerance is a few %.
   No display below 2.4 V, full duty compensation at 2.6 V.
7. LIS2DH12: register values in `src/lis2dh12.c` (low-power 10 Hz, ±2 g, 256 mg threshold, latched, active-low).
8. The TWI master works while the I2C pins keep their default pin configuration (input buffer enabled). This
   firmware doesn't test whether it also works with the buffer disabled.
9. CPU at 3.33 MHz (20 MHz / 6, factory default), within the limit at 1.8 V.

## Not done / open

- Nothing has run on hardware. The hardware-side code (ISR timing, I2C, sleep current, wake sources)
  is checked only by compiling with `-Wall -Wextra -Werror`.
- No instruction-level simulation was attempted (whether Debian's simavr 1.6 supports the tinyAVR 1-series wasn't checked).
- Accelerometer false-wake rate and the tilt thresholds need tuning on a wrist.
