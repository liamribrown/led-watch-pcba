#include "core.h"

void core_init(core_t *c, int16_t cal_x10)
{
    clock_init(&c->clk, cal_x10);
    ui_init(&c->ui, 1);                      /* time unknown after a battery change: set mode */
    for (uint8_t i = 0; i < FRAME_TICKS; i++) c->frames[0][i] = c->frames[1][i] = LED_NONE;
    c->front = 0; c->slot = 0; c->on_ticks = 4; c->battery_ok = 1;
}

void core_apply_seconds(core_t *c, uint8_t n) { while (n--) clock_tick(&c->clk); }

void core_wake_events(core_t *c, uint8_t pin_wake, uint8_t tilt)
{
    if (pin_wake) ui_poke(&c->ui);
    if (tilt) ui_poke(&c->ui);
}

uint8_t core_idle(const core_t *c, uint8_t tilt) { return !ui_awake(&c->ui) && !tilt; }

void core_start_awake(core_t *c, uint16_t vbat_mv)
{
    c->battery_ok = vbat_mv >= VBAT_EMPTY_MV;
    c->on_ticks = battery_on_ticks(vbat_mv);
    c->slot = 0;
}

uint8_t core_next_led(core_t *c)
{
    uint8_t led = c->frames[c->front][c->slot];
    if (++c->slot >= FRAME_TICKS) c->slot = 0;
    return led;
}

static void build_frame(core_t *c, ui_display_t disp)
{
    uint8_t back = c->front ^ 1;
    uint8_t *f = c->frames[back];
    if (disp == DISPLAY_TIME) {
        clockface_frame(c->clk.hour, c->clk.minute, c->clk.second,
                        ui_face_flags(&c->ui, SHOW_SECONDS), c->on_ticks, f);
    } else {
        for (uint8_t i = 0; i < FRAME_TICKS; i++) f[i] = LED_NONE;
        if (disp == DISPLAY_LOWBAT && (c->ui.blink_ms % 500) < 100)
            f[0] = led_minute(0);            /* short, dim blink at 12 o'clock */
    }
    c->front = back;                         /* single-byte write: atomic */
}

void core_step(core_t *c, uint8_t a, uint8_t b, uint8_t tilt)
{
    ui_in_t in = {0};
    in.a = a; in.b = b; in.tilt = tilt; in.battery_ok = c->battery_ok;
    ui_step(&c->ui, &in, &c->clk);
    build_frame(c, ui_display(&c->ui));
}

void core_tick_lines(uint8_t led, uint16_t *dir, uint16_t *out)
{
    uint8_t a, k;
    *dir = *out = 0;
    if (led_lines(led, &a, &k)) {
        *dir = (uint16_t)((1u << a) | (1u << k));
        *out = (uint16_t)(1u << a);
    }
}

uint8_t core_pa_bits(uint16_t mask) { return (uint8_t)((mask & 0x1Fu) << 3); }

uint8_t core_pb_bits(uint16_t mask)
{
    uint8_t r = 0;
    for (uint8_t line = 5; line < LED_LINES; line++)
        if (mask & (1u << line)) r |= (uint8_t)(1u << (12 - line));
    return r;
}
