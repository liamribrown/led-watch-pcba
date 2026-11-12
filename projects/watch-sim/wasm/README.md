# watch.wasm: the real LED watch firmware logic in the browser

Owner: 004. Built from `projects/led-watch/firmware/src/{ui,timekeep,clockface,led_map,tilt,battery,core}.c`
(unmodified, real headers) plus `sim.c`, which replaces `main.c`, `twi.c` and `lis2dh12.c`.
`core.c` is shared with the real `main.c` (frame building, UI step, wake events, scan-tick line masks), so the
decisions can't drift; `sim.c` mirrors only main()'s glue (sleep/wake, PIT, ADC, level-sensed wake pins).
This is a logic simulation: no electrical or battery model.

Build: `./build-wasm.sh` (needs `clang-19`, `lld-19`; freestanding, no WASI/imports) -> `../public/watch.wasm` (~5 KB).
Test: `~/.local/node/bin/node test-sim.mjs`.

Instantiate with `WebAssembly.instantiate(bytes, {})`; exports are plain ints, memory is exported.

| Export | Meaning |
|---|---|
| `sim_init()` | power-up (set mode at 12:00, first-set timeout, accel face up, vbat 3000) |
| `sim_set_inputs(a, b)` | button levels, 1 = pressed; wakes the watch like pin A's level-sensed wake |
| `sim_set_accel(x, y, z)` | int8 counts, 64 = 1 g, +Z out of the dial; a jump > 16 counts on any axis latches INT1 (wakes); a wake shows the time only if `tilt_face_up` |
| `sim_set_vbat_mv(mv)` | read through the 10-bit ADC conversion on each wake |
| `sim_advance_ms(ms)` | awake: 4 kHz scan tick by tick, 10 ms UI steps, 1 Hz PIT; asleep: jumps to the next PIT second |
| `sim_awake()`, `sim_state()`, `sim_display()` | 0/1; `UI_SLEEP/SHOW/SET/LOWBAT`; `DISPLAY_OFF/TIME/LOWBAT` |
| `sim_hour()` (0..11), `sim_minute()`, `sim_second()` | the clock |
| `sim_led_duty(i)` | ticks LED i was lit in the last FRAME_TICKS ticks |
| `sim_line_dir()`, `sim_line_out()` | 9-bit masks, bit n = line Ln: output / driven high, as of the last tick |
| `sim_tick_log(n)`, `sim_tick_log_len()` | LED lit n ticks ago (0 = latest, 255 = none), 64 entries |
| `sim_led_lines(i)` | `(anode << 4) | cathode` for LED i |
| `sim_const(id)` | constants from the firmware headers. ids in order: UI_SHOW_MS, UI_SET_HOLD_MS, UI_SET_IDLE_MS, UI_FIRST_SET_MS, UI_AFTER_SET_MS, UI_LOWBAT_MS, VBAT_EMPTY_MV, VBAT_FRESH_MV, FRAME_TICKS, LED_COUNT, LED_LINES, TICK_HZ, UI_STEP_MS, UI_SLEEP, UI_SHOW, UI_SET, UI_LOWBAT, DISPLAY_OFF, DISPLAY_TIME, DISPLAY_LOWBAT, LED_MINUTE_FIRST, LED_HOUR_FIRST, LED_NONE (0..22) |

LED numbers: 0..59 minute ring, 60..71 hour ring, 12 o'clock first, clockwise. Sleeping runs at up to 1 s per
inner step, so `sim_advance_ms(3600000)` is cheap; awake time costs 4 steps per ms.
Not covered by the simulation: ISR timing, I2C, real accelerometer filtering (a simple jump threshold stands in).
