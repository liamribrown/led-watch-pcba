/* Logic shared by the real firmware (main.c) and the browser simulation (watch-sim/wasm/sim.c).
 * Pure C, host-testable. Everything that decides what the watch does lives here or in the modules it
 * calls; main.c and sim.c only add the hardware (or the simulated hardware) around it. */
#ifndef CORE_H
#define CORE_H
#include <stdint.h>
#include "led_map.h"
#include "clockface.h"
#include "timekeep.h"
#include "battery.h"
#include "ui.h"

#ifndef SHOW_SECONDS
#define SHOW_SECONDS 1      /* dim seconds dot while the time is shown */
#endif
#define TICK_HZ        4000U
#define TICKS_PER_STEP (TICK_HZ / 1000U * UI_STEP_MS)   /* 40 */

typedef struct {
    clock_t_ clk;
    ui_t ui;
    uint8_t frames[2][FRAME_TICKS];
    volatile uint8_t front;    /* frame the scan tick reads; the other one is being built */
    uint8_t slot;              /* next tick in the frame */
    uint8_t on_ticks;          /* hand-LED ticks per frame, from the battery voltage */
    uint8_t battery_ok;
} core_t;

void core_init(core_t *c, int16_t cal_x10);
/* PIT seconds that arrived since the last call. */
void core_apply_seconds(core_t *c, uint8_t n);
/* Wake events seen at the top of the main loop: pin_wake = a wake pin fired, tilt = a qualified tilt. */
void core_wake_events(core_t *c, uint8_t pin_wake, uint8_t tilt);
/* 1 = nothing keeps the watch awake: go to sleep. */
uint8_t core_idle(const core_t *c, uint8_t tilt);
/* Just woke: take the battery reading (mV), set the LED duty, restart the scan. */
void core_start_awake(core_t *c, uint16_t vbat_mv);
/* The 4 kHz scan tick: the LED to light on this tick (LED_NONE = none). */
uint8_t core_next_led(core_t *c);
/* One UI step (every UI_STEP_MS while awake): run the state machine, build the next frame. */
void core_step(core_t *c, uint8_t a, uint8_t b, uint8_t tilt);

/* Charlieplex lines for one tick, as 9-bit masks (bit n = line Ln): after "drain, float" the cathode is
 * driven low and the anode high. LED_NONE (or invalid) leaves every line floating (dir = out = 0). */
void core_tick_lines(uint8_t led, uint16_t *dir, uint16_t *out);
/* The same masks as port bits: lines L0..L4 are PORTA bits 3..7, L5..L8 are PORTB bits 7..4. */
uint8_t core_pa_bits(uint16_t mask);
uint8_t core_pb_bits(uint16_t mask);

#endif
