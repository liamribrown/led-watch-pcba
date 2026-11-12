/* Host unit tests for the hardware-independent firmware modules. Built and run by ../build.sh. */
#include <stdio.h>
#include <string.h>
#include "led_map.h"
#include "clockface.h"
#include "timekeep.h"
#include "battery.h"
#include "tilt.h"
#include "ui.h"
#include "core.h"

static int failures, checks;
#define CHECK(cond) do { checks++; if (!(cond)) { failures++; \
    printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); } } while (0)
#define CHECK_EQ(a, b) do { long _a = (long)(a), _b = (long)(b); checks++; if (_a != _b) { failures++; \
    printf("FAIL %s:%d: %s == %ld, expected %ld\n", __FILE__, __LINE__, #a, _a, _b); } } while (0)

/* ---------------- charlieplex mapping ---------------- */
static void test_led_lines(void)
{
    uint8_t seen[LED_LINES][LED_LINES] = {{0}};
    for (uint8_t led = 0; led < LED_COUNT; led++) {
        uint8_t a = 99, c = 99;
        CHECK(led_lines(led, &a, &c));
        CHECK(a < LED_LINES && c < LED_LINES);
        CHECK(a != c);
        CHECK(!seen[a][c]);                 /* every LED has its own (anode, cathode) pair */
        seen[a][c] = 1;
    }
    /* all 9*8 ordered pairs are used: no line pair left unused or doubled */
    int used = 0;
    for (int a = 0; a < LED_LINES; a++) for (int c = 0; c < LED_LINES; c++) used += seen[a][c];
    CHECK_EQ(used, 72);

    /* spot checks against the board's PINMAP.md LED table */
    uint8_t a, c;
    CHECK(led_lines(0, &a, &c));  CHECK_EQ(a, 2); CHECK_EQ(c, 8);   /* D1 */
    CHECK(led_lines(2, &a, &c));  CHECK_EQ(a, 5); CHECK_EQ(c, 3);   /* D3 */
    CHECK(led_lines(29, &a, &c)); CHECK_EQ(a, 4); CHECK_EQ(c, 3);   /* D30 */
    CHECK(led_lines(60, &a, &c)); CHECK_EQ(a, 5); CHECK_EQ(c, 2);   /* D61, first hour LED */
    CHECK(led_lines(71, &a, &c)); CHECK_EQ(a, 8); CHECK_EQ(c, 4);   /* D72 */
    CHECK(!led_lines(72, &a, &c));
    CHECK(!led_lines(LED_NONE, &a, &c));
}

static void test_led_numbering(void)
{
    CHECK_EQ(led_minute(0), 0);
    CHECK_EQ(led_minute(59), 59);
    CHECK_EQ(led_minute(60), 0);
    CHECK_EQ(led_hour(0), 60);
    CHECK_EQ(led_hour(11), 71);
    CHECK_EQ(led_hour(12), 60);
    CHECK_EQ(led_hour(15), 63);
}

/* ---------------- time -> frame ---------------- */
static int count(const uint8_t *s, uint8_t led)
{
    int n = 0;
    for (int i = 0; i < FRAME_TICKS; i++) n += s[i] == led;
    return n;
}

static void test_clockface(void)
{
    uint8_t s[FRAME_TICKS];

    /* 3:15:30, seconds on, fresh battery (4 ticks per hand) */
    CHECK_EQ(clockface_frame(3, 15, 30, FACE_SHOW_SECONDS, 4, s), 9);
    CHECK_EQ(count(s, led_hour(3)), 4);
    CHECK_EQ(count(s, led_minute(15)), 4);
    CHECK_EQ(count(s, led_minute(30)), 1);
    CHECK_EQ(count(s, LED_NONE), FRAME_TICKS - 9);

    /* seconds hidden when it overlaps the minute LED */
    CHECK_EQ(clockface_frame(3, 15, 15, FACE_SHOW_SECONDS, 4, s), 8);
    /* seconds off */
    CHECK_EQ(clockface_frame(3, 15, 30, 0, 4, s), 8);
    CHECK_EQ(count(s, led_minute(30)), 0);
    /* blink phases */
    CHECK_EQ(clockface_frame(3, 15, 30, FACE_HIDE_HOUR, 4, s), 4);
    CHECK_EQ(count(s, led_hour(3)), 0);
    CHECK_EQ(clockface_frame(3, 15, 30, FACE_HIDE_HOUR | FACE_HIDE_MINUTE, 4, s), 0);
    /* low battery: 7 ticks each, and on_ticks is clamped so the frame never overflows */
    CHECK_EQ(clockface_frame(11, 59, 0, FACE_SHOW_SECONDS, 7, s), 15);
    CHECK_EQ(clockface_frame(11, 59, 0, FACE_SHOW_SECONDS, 200, s), 15);

    /* exhaustive: every time of a 12-hour day gives a valid frame */
    for (int h = 0; h < 12; h++)
        for (int m = 0; m < 60; m++)
            for (int sec = 0; sec < 60; sec += 7) {
                uint8_t lit = clockface_frame((uint8_t)h, (uint8_t)m, (uint8_t)sec,
                                              FACE_SHOW_SECONDS, 7, s);
                CHECK(lit <= FRAME_TICKS);
                for (int i = 0; i < FRAME_TICKS; i++) {
                    uint8_t a, c;
                    if (i < lit) CHECK(led_lines(s[i], &a, &c));
                    else CHECK(s[i] == LED_NONE);
                }
                CHECK_EQ(count(s, (uint8_t)(LED_HOUR_FIRST + h)), 7);
                CHECK_EQ(count(s, (uint8_t)m), 7);
            }
}

/* ---------------- clock and calibration ---------------- */
static long secs_of(const clock_t_ *c) { return c->hour * 3600L + c->minute * 60L + c->second; }

static void test_clock(void)
{
    clock_t_ c;
    clock_init(&c, 0);
    c.hour = 11; c.minute = 59; c.second = 59;
    clock_tick(&c);
    CHECK_EQ(c.hour, 0); CHECK_EQ(c.minute, 0); CHECK_EQ(c.second, 0);

    clock_init(&c, 0);
    for (long i = 0; i < 43200; i++) clock_tick(&c);       /* exactly 12 h */
    CHECK_EQ(secs_of(&c), 0);

    /* +10.0 ppm (crystal slow): one extra second per 100 000 s */
    const long N = 1000000;
    clock_init(&c, 100);
    for (long i = 0; i < N; i++) clock_tick(&c);
    CHECK_EQ(secs_of(&c), (N + 10) % 43200);

    /* -10.0 ppm (crystal fast) */
    clock_init(&c, -100);
    for (long i = 0; i < N; i++) clock_tick(&c);
    CHECK_EQ(secs_of(&c), (N - 10) % 43200);

    /* +0.5 ppm resolution: one second per 2 000 000 s */
    clock_init(&c, 5);
    for (long i = 0; i < 2000000; i++) clock_tick(&c);
    CHECK_EQ(secs_of(&c), (2000000 + 1) % 43200);

    /* setting */
    clock_init(&c, 0);
    c.hour = 11; c.minute = 59; c.second = 42;
    clock_step_hour(&c);   CHECK_EQ(c.hour, 0);
    clock_step_minute(&c); CHECK_EQ(c.minute, 0); CHECK_EQ(c.second, 0);

    CHECK_EQ(clock_cal_from_bytes(0xFF, 0xFF), 0);
    CHECK_EQ(clock_cal_from_bytes(0x64, 0x00), 100);
    CHECK_EQ(clock_cal_from_bytes(0x9C, 0xFF), -100);
}

/* ---------------- battery ---------------- */
static void test_battery(void)
{
    CHECK_EQ(battery_mv_from_adc(375), 3001);   /* 1100 * 1023 / 375 */
    CHECK_EQ(battery_mv_from_adc(469), 2399);
    CHECK_EQ(battery_mv_from_adc(1023), 1100);
    CHECK(battery_mv_from_adc(0) > 5000);
    CHECK_EQ(battery_on_ticks(3300), 4);
    CHECK_EQ(battery_on_ticks(3000), 4);
    CHECK_EQ(battery_on_ticks(2800), 6);
    CHECK_EQ(battery_on_ticks(2600), 7);
    CHECK_EQ(battery_on_ticks(2000), 7);
    for (uint16_t mv = 2400; mv < 3300; mv++)
        CHECK(battery_on_ticks(mv + 1) <= battery_on_ticks(mv));   /* never brighter as V falls */
}

/* ---------------- tilt ---------------- */
static void test_tilt(void)
{
    CHECK(tilt_face_up(0, 0, 62));      /* 1 g straight up */
    CHECK(!tilt_face_up(0, 0, -62));    /* face down */
    CHECK(!tilt_face_up(62, 0, 0));     /* arm hanging */
    CHECK(tilt_face_up(31, -31, 37));   /* edges of the window */
    CHECK(!tilt_face_up(32, 0, 50));
    CHECK(!tilt_face_up(0, 0, 36));
}

/* ---------------- UI state machine ---------------- */
static ui_in_t in;
static void run(ui_t *u, clock_t_ *c, uint8_t a, uint8_t b, int ms)
{
    in.a = a; in.b = b;
    for (int t = 0; t < ms; t += UI_STEP_MS) { ui_step(u, &in, c); in.tilt = 0; }
}

static void test_ui(void)
{
    ui_t u; clock_t_ c;
    in = (ui_in_t){ .battery_ok = 1 };

    /* power-up: set mode, times out after 60 s idle, shows 2 s, sleeps */
    clock_init(&c, 0);
    ui_init(&u, 1);
    CHECK_EQ(u.state, UI_SET);
    CHECK_EQ(ui_display(&u), DISPLAY_TIME);
    run(&u, &c, 0, 0, UI_FIRST_SET_MS - 10);  CHECK_EQ(u.state, UI_SET);
    run(&u, &c, 0, 0, 10);                    CHECK_EQ(u.state, UI_SHOW);
    run(&u, &c, 0, 0, UI_AFTER_SET_MS);       CHECK_EQ(u.state, UI_SLEEP);
    CHECK_EQ(ui_display(&u), DISPLAY_OFF);

    /* a 10 ms glitch is not a press */
    run(&u, &c, 1, 0, 10); run(&u, &c, 0, 0, 30);
    CHECK_EQ(u.state, UI_SLEEP);

    /* press A: shown 5 s after release, then asleep */
    run(&u, &c, 1, 0, 50);                    CHECK_EQ(u.state, UI_SHOW);
    run(&u, &c, 0, 0, UI_SHOW_MS - 50);       CHECK_EQ(u.state, UI_SHOW);
    run(&u, &c, 0, 0, 100);                   CHECK_EQ(u.state, UI_SLEEP);
    CHECK(!ui_awake(&u));

    /* ui_poke keeps us awake for the debounce window only */
    ui_poke(&u);                              CHECK(ui_awake(&u));
    run(&u, &c, 0, 0, UI_WAKE_GRACE * UI_STEP_MS);
    CHECK(!ui_awake(&u));

    /* tilt shows the time, with the seconds flag */
    in.tilt = 1; run(&u, &c, 0, 0, 10);       CHECK_EQ(u.state, UI_SHOW);
    CHECK(ui_face_flags(&u, 1) & FACE_SHOW_SECONDS);
    CHECK_EQ(ui_face_flags(&u, 0), 0);
    run(&u, &c, 0, 0, UI_SHOW_MS);            CHECK_EQ(u.state, UI_SLEEP);

    /* empty battery: short low-battery blink instead of the time */
    in.battery_ok = 0;
    run(&u, &c, 1, 0, 30);                    CHECK_EQ(u.state, UI_LOWBAT);
    CHECK_EQ(ui_display(&u), DISPLAY_LOWBAT);
    run(&u, &c, 0, 0, UI_LOWBAT_MS);          CHECK_EQ(u.state, UI_SLEEP);
    in.battery_ok = 1;

    /* set mode: hold A+B 2 s; buttons ignored until both are released */
    clock_init(&c, 0); c.hour = 4; c.minute = 20; c.second = 33;
    run(&u, &c, 1, 1, UI_SET_HOLD_MS + 20);   CHECK_EQ(u.state, UI_SET);
    run(&u, &c, 1, 1, 500);                   CHECK_EQ(c.hour, 4); CHECK_EQ(c.minute, 20);
    run(&u, &c, 0, 0, 50);
    run(&u, &c, 1, 0, 50); run(&u, &c, 0, 0, 50);       /* A: hour + 1 */
    CHECK_EQ(c.hour, 5); CHECK_EQ(c.minute, 20);
    run(&u, &c, 0, 1, 50); run(&u, &c, 0, 0, 50);       /* B: minute + 1, seconds zeroed */
    CHECK_EQ(c.minute, 21); CHECK_EQ(c.second, 0);
    /* hold B: first step on press, then repeats every 150 ms after 600 ms */
    run(&u, &c, 0, 1, 20 + UI_REPEAT_DELAY_MS + 3 * UI_REPEAT_MS);
    CHECK_EQ(c.minute, 25);
    run(&u, &c, 0, 0, 50);
    /* blinking in set mode */
    int on = 0, off = 0;
    for (int t = 0; t < 1000; t += 10) {
        run(&u, &c, 0, 0, 10);
        if (ui_face_flags(&u, 1) == 0) on++;
        else if (ui_face_flags(&u, 1) == (FACE_HIDE_HOUR | FACE_HIDE_MINUTE)) off++;
    }
    CHECK(on > 40 && off > 40);
    /* idle 5 s: saves, shows 2 s, sleeps */
    run(&u, &c, 0, 0, UI_SET_IDLE_MS);        CHECK_EQ(u.state, UI_SHOW);
    run(&u, &c, 0, 0, UI_AFTER_SET_MS);       CHECK_EQ(u.state, UI_SLEEP);
    CHECK_EQ(c.hour, 5); CHECK_EQ(c.minute, 25);

    /* a button stuck closed must not keep the MCU awake (002 review, finding 1) */
    ui_t u2; clock_t_ c2;
    clock_init(&c2, 0);
    ui_init(&u2, 0);
    run(&u2, &c2, 1, 0, 50);                    CHECK_EQ(u2.state, UI_SHOW);
    run(&u2, &c2, 1, 0, UI_SHOW_MS + 200);      CHECK_EQ(u2.state, UI_SLEEP);
    run(&u2, &c2, 1, 0, UI_WAKE_GRACE * UI_STEP_MS);
    CHECK(!ui_awake(&u2));
    /* ...and after sleeping with it held, a real press later is still a new press */
    ui_sleep_reset(&u2);
    run(&u2, &c2, 0, 0, 50);
    run(&u2, &c2, 1, 0, 50);                    CHECK_EQ(u2.state, UI_SHOW);
    run(&u2, &c2, 0, 0, UI_SHOW_MS + 200);      CHECK_EQ(u2.state, UI_SLEEP);
    /* same for B alone and for A+B held while SHOW times out (set mode not entered below 2 s) */
    run(&u2, &c2, 0, 1, 3000);                  CHECK_EQ(u2.state, UI_SLEEP);
    CHECK(!ui_awake(&u2) || u2.grace > 0);

    /* holding A+B from sleep never steps the time by itself */
    run(&u, &c, 1, 1, UI_SET_HOLD_MS + 3000);
    CHECK_EQ(u.state, UI_SET); CHECK_EQ(c.hour, 5); CHECK_EQ(c.minute, 25);
}

int main(void)
{
    test_led_lines();
    test_led_numbering();
    test_clockface();
    test_clock();
    test_battery();
    test_tilt();
    test_ui();
    /* core.c: the line masks used by the scan ISR (main.c) and the simulation (watch-sim) */
    for (unsigned led = 0; led < LED_COUNT; led++) {
        uint8_t a, k; uint16_t dir, out;
        CHECK(led_lines((uint8_t)led, &a, &k));
        core_tick_lines((uint8_t)led, &dir, &out);
        CHECK_EQ(dir, (1u << a) | (1u << k));
        CHECK_EQ(out, 1u << a);
        /* the old line_drive() rule: L0..L4 = PA bit line+3, L5..L8 = PB bit 12-line */
        uint8_t pa = 0, pb = 0;
        for (unsigned l = 0; l < LED_LINES; l++) if (dir & (1u << l)) {
            if (l < 5) pa |= (uint8_t)(1u << (l + 3)); else pb |= (uint8_t)(1u << (12 - l));
        }
        CHECK_EQ(core_pa_bits(dir), pa);
        CHECK_EQ(core_pb_bits(dir), pb);
        CHECK((core_pa_bits(dir) & ~0xF8) == 0 && (core_pb_bits(dir) & ~0xF0) == 0);
    }
    { uint16_t d = 1, o = 1; core_tick_lines(LED_NONE, &d, &o); CHECK(d == 0 && o == 0); }
    { /* core loop: wake, show, sleep */
        core_t c; core_init(&c, 0);
        CHECK(c.ui.state == UI_SET);
        core_start_awake(&c, 3000); CHECK_EQ(c.on_ticks, 4); CHECK(c.battery_ok);
        core_start_awake(&c, 2300); CHECK(!c.battery_ok);
    }
    printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
