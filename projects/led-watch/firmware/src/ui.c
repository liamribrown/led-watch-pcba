#include "ui.h"
#include "clockface.h"

#define DEB_MAX 2  /* 2 steps = 20 ms stable */

static void enter(ui_t *u, ui_state_t s, uint16_t ms)
{
    u->state = s;
    u->timer_ms = ms;
    u->blink_ms = 0;
}

static void enter_set(ui_t *u, uint16_t limit_ms, uint8_t wait_release)
{
    enter(u, UI_SET, 0);
    u->set_limit_ms = limit_ms;
    u->wait_release = wait_release;
    u->repeat_ms = 0;
    u->both_ms = 0;
}

void ui_init(ui_t *u, uint8_t time_unset)
{
    *u = (ui_t){0};
    if (time_unset) enter_set(u, UI_FIRST_SET_MS, 0);
    else enter(u, UI_SLEEP, 0);
}

void ui_poke(ui_t *u) { u->grace = UI_WAKE_GRACE; }

/* Debounce one button; returns 1 on a press edge. */
static uint8_t debounce(uint8_t raw, uint8_t *integ, uint8_t *level)
{
    if (raw) { if (*integ < DEB_MAX) (*integ)++; }
    else if (*integ > 0) (*integ)--;
    if (*integ == DEB_MAX && !*level) { *level = 1; return 1; }
    if (*integ == 0 && *level) *level = 0;
    return 0;
}

static void show(ui_t *u, uint8_t battery_ok, uint16_t ms)
{
    if (battery_ok) enter(u, UI_SHOW, ms);
    else enter(u, UI_LOWBAT, UI_LOWBAT_MS);
}

static uint16_t count_down(uint16_t t) { return t > UI_STEP_MS ? t - UI_STEP_MS : 0; }

void ui_step(ui_t *u, const ui_in_t *in, clock_t_ *clk)
{
    uint8_t press_a = debounce(in->a, &u->deb_a, &u->a);
    uint8_t press_b = debounce(in->b, &u->deb_b, &u->b);
    if (u->grace) u->grace--;
    u->blink_ms += UI_STEP_MS;

    /* A+B held for 2 s enters set mode from SLEEP or SHOW */
    if (u->state != UI_SET) {
        u->both_ms = (u->a && u->b) ? u->both_ms + UI_STEP_MS : 0;
        if (u->both_ms >= UI_SET_HOLD_MS) { enter_set(u, UI_SET_IDLE_MS, 1); return; }
    }

    switch (u->state) {
    case UI_SLEEP:
        if (press_a || in->tilt) show(u, in->battery_ok, UI_SHOW_MS);
        break;

    case UI_SHOW:
        if (press_a || in->tilt) u->timer_ms = UI_SHOW_MS;   /* extend */
        else if (!(u->a && u->b)) {
            u->timer_ms = count_down(u->timer_ms);
            if (!u->timer_ms) enter(u, UI_SLEEP, 0);
        }
        break;

    case UI_LOWBAT:
        u->timer_ms = count_down(u->timer_ms);
        if (!u->timer_ms) enter(u, UI_SLEEP, 0);
        break;

    case UI_SET:
        if (u->wait_release) {
            if (!u->a && !u->b) u->wait_release = 0;
            u->timer_ms = 0;
            break;
        }
        if (press_a) { clock_step_hour(clk); u->timer_ms = 0; u->blink_ms = 0; }
        if (press_b) { clock_step_minute(clk); u->timer_ms = 0; u->blink_ms = 0; u->repeat_ms = 0; }
        else if (u->b) {
            u->repeat_ms += UI_STEP_MS;
            if (u->repeat_ms >= UI_REPEAT_DELAY_MS + UI_REPEAT_MS) {
                u->repeat_ms = UI_REPEAT_DELAY_MS;
                clock_step_minute(clk);
                u->blink_ms = 0;
            }
            u->timer_ms = 0;
        }
        if (u->a) u->timer_ms = 0;
        if (!u->a && !u->b) {
            u->timer_ms += UI_STEP_MS;
            if (u->timer_ms >= u->set_limit_ms) show(u, in->battery_ok, UI_AFTER_SET_MS);
        }
        break;
    }
}

/* A button held in SLEEP (stuck switch, sleeve) must not keep the MCU awake. */
uint8_t ui_awake(const ui_t *u) { return u->state != UI_SLEEP || u->grace > 0; }

void ui_sleep_reset(ui_t *u) { u->a = u->b = 0; u->deb_a = u->deb_b = 0; u->both_ms = 0; }

ui_display_t ui_display(const ui_t *u)
{
    switch (u->state) {
    case UI_SHOW: case UI_SET: return DISPLAY_TIME;
    case UI_LOWBAT:            return DISPLAY_LOWBAT;
    default:                   return DISPLAY_OFF;
    }
}

uint8_t ui_face_flags(const ui_t *u, uint8_t show_seconds)
{
    if (u->state == UI_SET)   /* both hands blink 250 ms on / 250 ms off */
        return (u->blink_ms % 500) >= 250 ? (FACE_HIDE_HOUR | FACE_HIDE_MINUTE) : 0;
    return show_seconds ? FACE_SHOW_SECONDS : 0;
}
