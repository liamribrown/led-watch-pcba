/* Simulated hardware layer for the LED watch firmware, compiled to WebAssembly.
 * Replaces main.c / twi.c / lis2dh12.c; all decisions come from the real firmware modules and from
 * src/core.c (shared with main.c). main_iter() below mirrors main()'s loop, step by step.
 * This simulates firmware LOGIC (buttons, tilt, sleep/wake, scan walk). No electrical or battery model. */
#include <stdint.h>
#include "core.h"
#include "tilt.h"

#define EXPORT __attribute__((visibility("default")))

/* freestanding: the compiler may emit these for struct copies / zeroing */
void *memset(void *d, int v, __SIZE_TYPE__ n) { uint8_t *p = d; while (n--) *p++ = (uint8_t)v; return d; }
void *memcpy(void *d, const void *s, __SIZE_TYPE__ n) { uint8_t *p = d; const uint8_t *q = s; while (n--) *p++ = *q++; return d; }

#define LOG_N 64
#define INT_THS_COUNTS 16        /* LIS2DH12 THS register 0x10 at +-2 g low power (src/lis2dh12.c): 256 mg */

static core_t core;
/* what main.c keeps in ISR-shared variables */
static uint8_t pending_secs, wake_pins, ticks;
static uint8_t awake_before, sleeping, pending_tilt;   /* pending_tilt: this loop pass's tilt, used by its UI step */
/* inputs and simulated pins */
static uint8_t btn_a, btn_b;                           /* 1 = pressed */
static int8_t ax, ay, az;
static uint8_t int_latched;                            /* LIS2DH12 INT1 latch (pin low while set) */
static uint8_t a_armed, int_armed;                     /* wake_arm(): level sensing active */
static uint16_t vbat_mv = 3000;
static uint16_t pit_ticks;                             /* scan ticks since the last PIT second */
static uint16_t line_dir, line_out;
static uint8_t tick_log[LOG_N], log_pos;               /* LED index per tick (LED_NONE = none) */
static uint8_t frame_ring[FRAME_TICKS], ring_pos;

static void record_tick(uint8_t led)
{
    uint16_t d, o;
    core_tick_lines(led, &d, &o);
    line_dir = d; line_out = o;
    tick_log[log_pos] = led; log_pos = (uint8_t)((log_pos + 1) % LOG_N);
    frame_ring[ring_pos] = led; ring_pos = (uint8_t)((ring_pos + 1) % FRAME_TICKS);
}

/* ---- simulated hardware ---- */
static uint8_t a_pin_high(void) { return !btn_a; }
static uint8_t int_pin_high(void) { return !int_latched; }

static uint8_t acc_check(void)             /* lis_read clears the latch */
{
    int_latched = 0;
    return tilt_face_up(ax, ay, az);
}

static uint16_t battery_read_mv(void)      /* same conversion as main.c, quantised by the 10-bit ADC */
{
    uint32_t raw = (1100UL * 1023UL + vbat_mv / 2) / vbat_mv;
    if (raw > 1023) raw = 1023;
    return battery_mv_from_adc((uint16_t)raw);
}

static void wake_arm(void)                 /* as main.c: arm only pins that are currently high */
{
    a_armed = a_pin_high();
    int_armed = int_pin_high();
}

static void check_wake_pins(void)          /* level-sense ISR: fires while armed and the pin is low */
{
    if (!sleeping) return;
    if (int_armed && !int_pin_high()) { int_armed = 0; wake_pins |= 2 | 1; }
    if (a_armed && !a_pin_high())     { a_armed = 0; wake_pins |= 1; }
}

static void scan_stop(void) { for (uint8_t i = 0; i < LOG_N; i++) tick_log[i] = LED_NONE;
                              for (uint8_t i = 0; i < FRAME_TICKS; i++) frame_ring[i] = LED_NONE;
                              line_dir = line_out = 0; }

static void go_to_sleep(void)
{
    scan_stop();
    ui_sleep_reset(&core.ui);
    wake_arm();
    sleeping = (!wake_pins && !pending_secs);
}

/* One pass of main()'s loop, up to where it waits for the next 10 ms. Returns 1 if the watch went to sleep. */
static void main_iter(void)
{
    uint8_t n = pending_secs; pending_secs = 0;
    core_apply_seconds(&core, n);

    uint8_t tilt = 0, w = wake_pins; wake_pins = 0;
    if (!int_pin_high()) w |= 2;                          /* stuck-low INT1 is retried on every pass */
    if (w & 2) tilt = acc_check();
    core_wake_events(&core, w & 1, tilt);

    if (core_idle(&core, tilt)) { awake_before = 0; go_to_sleep(); return; }
    sleeping = 0;
    if (!awake_before) {
        core_start_awake(&core, battery_read_mv());
        ticks = 0;
        awake_before = 1;
    }
    pending_tilt = tilt;
}

static void run_main(void)                 /* main loop passes until it waits or sleeps */
{
    for (uint8_t guard = 0; guard < 8; guard++) {
        main_iter();
        if (sleeping || awake_before) return;
    }
}

static void pit_second(void)
{
    if (pending_secs < 255) pending_secs++;
    if (sleeping) { sleeping = 0; run_main(); }
}

/* ---- API ---- */
EXPORT void sim_init(void)
{
    core_init(&core, 0);
    pending_secs = wake_pins = ticks = awake_before = pending_tilt = 0;
    sleeping = 0; btn_a = btn_b = 0; ax = ay = 0; az = 64; int_latched = 0;   /* 64 counts = 1 g, face up */
    pit_ticks = 0;
    scan_stop();
    acc_check();                                      /* main(): clear a latch left from start-up */
    run_main();
}

EXPORT void sim_set_inputs(uint8_t a, uint8_t b)
{
    btn_a = a ? 1 : 0; btn_b = b ? 1 : 0;
    check_wake_pins();
    if (wake_pins && sleeping) { sleeping = 0; run_main(); }
}

EXPORT void sim_set_accel(int8_t x, int8_t y, int8_t z)
{
    int dx = x - ax, dy = y - ay, dz = z - az;
    if (dx < 0) dx = -dx;
    if (dy < 0) dy = -dy;
    if (dz < 0) dz = -dz;
    ax = x; ay = y; az = z;
    if (dx > INT_THS_COUNTS || dy > INT_THS_COUNTS || dz > INT_THS_COUNTS) int_latched = 1;
    check_wake_pins();
    if (wake_pins && sleeping) { sleeping = 0; run_main(); }
}

EXPORT void sim_set_vbat_mv(uint16_t mv) { vbat_mv = mv ? mv : 1; }

/* Run for ms milliseconds of watch time. Awake: scan tick by tick. Asleep: jump to the next PIT second. */
EXPORT void sim_advance_ms(uint32_t ms)
{
    uint32_t left = ms * (TICK_HZ / 1000U);           /* in scan ticks */
    while (left) {
        if (sleeping) {
            uint32_t to_pit = TICK_HZ - pit_ticks;
            uint32_t d = left < to_pit ? left : to_pit;
            left -= d; pit_ticks = (uint16_t)(pit_ticks + d);
            if (pit_ticks >= TICK_HZ) { pit_ticks = 0; pit_second(); }
            continue;
        }
        record_tick(core_next_led(&core));
        ticks++; left--;
        if (++pit_ticks >= TICK_HZ) { pit_ticks = 0; pit_second(); }
        if (!sleeping && ticks >= TICKS_PER_STEP) {   /* main(): wait for 40 ticks, then the UI step */
            ticks = 0;
            core_step(&core, btn_a, btn_b, pending_tilt);
            run_main();
        }
    }
}

EXPORT uint8_t sim_awake(void) { return !sleeping; }
EXPORT uint8_t sim_state(void) { return (uint8_t)core.ui.state; }
EXPORT uint8_t sim_display(void) { return (uint8_t)ui_display(&core.ui); }
EXPORT uint8_t sim_hour(void) { return core.clk.hour; }
EXPORT uint8_t sim_minute(void) { return core.clk.minute; }
EXPORT uint8_t sim_second(void) { return core.clk.second; }
EXPORT uint8_t sim_led_duty(uint8_t led)
{
    uint8_t n = 0;
    for (uint8_t i = 0; i < FRAME_TICKS; i++) if (frame_ring[i] == led) n++;
    return n;
}
EXPORT uint16_t sim_line_dir(void) { return line_dir; }   /* bit n = line Ln is an output */
EXPORT uint16_t sim_line_out(void) { return line_out; }   /* bit n = line Ln driven high */
/* The LED lit n ticks ago (0 = the latest tick), LED_NONE (255) if none; anode/cathode via sim_led_lines. */
EXPORT uint8_t sim_tick_log(uint8_t n) { return tick_log[(uint8_t)((log_pos + LOG_N - 1 - (n % LOG_N)) % LOG_N)]; }
EXPORT uint8_t sim_tick_log_len(void) { return LOG_N; }
/* Charlieplex lines of an LED: (anode << 4) | cathode, 255 if invalid. */
EXPORT uint8_t sim_led_lines(uint8_t led)
{
    uint8_t a, c;
    return led_lines(led, &a, &c) ? (uint8_t)((a << 4) | c) : 255;
}

enum { C_UI_SHOW_MS, C_UI_SET_HOLD_MS, C_UI_SET_IDLE_MS, C_UI_FIRST_SET_MS, C_UI_AFTER_SET_MS, C_UI_LOWBAT_MS,
       C_VBAT_EMPTY_MV, C_VBAT_FRESH_MV, C_FRAME_TICKS, C_LED_COUNT, C_LED_LINES, C_TICK_HZ, C_UI_STEP_MS,
       C_UI_SLEEP, C_UI_SHOW, C_UI_SET, C_UI_LOWBAT, C_DISPLAY_OFF, C_DISPLAY_TIME, C_DISPLAY_LOWBAT,
       C_LED_MINUTE_FIRST, C_LED_HOUR_FIRST, C_LED_NONE };
EXPORT int32_t sim_const(int32_t id)
{
    switch (id) {
    case C_UI_SHOW_MS: return UI_SHOW_MS;           case C_UI_SET_HOLD_MS: return UI_SET_HOLD_MS;
    case C_UI_SET_IDLE_MS: return UI_SET_IDLE_MS;   case C_UI_FIRST_SET_MS: return UI_FIRST_SET_MS;
    case C_UI_AFTER_SET_MS: return UI_AFTER_SET_MS; case C_UI_LOWBAT_MS: return UI_LOWBAT_MS;
    case C_VBAT_EMPTY_MV: return VBAT_EMPTY_MV;     case C_VBAT_FRESH_MV: return VBAT_FRESH_MV;
    case C_FRAME_TICKS: return FRAME_TICKS;         case C_LED_COUNT: return LED_COUNT;
    case C_LED_LINES: return LED_LINES;             case C_TICK_HZ: return TICK_HZ;
    case C_UI_STEP_MS: return UI_STEP_MS;
    case C_UI_SLEEP: return UI_SLEEP;               case C_UI_SHOW: return UI_SHOW;
    case C_UI_SET: return UI_SET;                   case C_UI_LOWBAT: return UI_LOWBAT;
    case C_DISPLAY_OFF: return DISPLAY_OFF;         case C_DISPLAY_TIME: return DISPLAY_TIME;
    case C_DISPLAY_LOWBAT: return DISPLAY_LOWBAT;
    case C_LED_MINUTE_FIRST: return LED_MINUTE_FIRST; case C_LED_HOUR_FIRST: return LED_HOUR_FIRST;
    case C_LED_NONE: return LED_NONE;
    default: return -1;
    }
}
