#include "timekeep.h"

void clock_init(clock_t_ *c, int16_t cal_x10)
{
    c->hour = 0; c->minute = 0; c->second = 0;
    c->cal_x10 = cal_x10;
    c->cal_acc = 0;
}

void clock_add_seconds(clock_t_ *c, uint8_t n)
{
    while (n--) {
        if (++c->second < 60) continue;
        c->second = 0;
        if (++c->minute < 60) continue;
        c->minute = 0;
        if (++c->hour >= 12) c->hour = 0;
    }
}

void clock_tick(clock_t_ *c)
{
    uint8_t n = 1;
    c->cal_acc += c->cal_x10;
    if (c->cal_acc >= CAL_ONE_SECOND) {        /* crystal slow: insert a second */
        c->cal_acc -= CAL_ONE_SECOND;
        n = 2;
    } else if (c->cal_acc <= -CAL_ONE_SECOND) { /* crystal fast: drop a second */
        c->cal_acc += CAL_ONE_SECOND;
        n = 0;
    }
    clock_add_seconds(c, n);
}

void clock_step_hour(clock_t_ *c)   { c->hour = (uint8_t)((c->hour + 1) % 12); }
void clock_step_minute(clock_t_ *c) { c->minute = (uint8_t)((c->minute + 1) % 60); c->second = 0; c->cal_acc = 0; }

int16_t clock_cal_from_bytes(uint8_t lo, uint8_t hi)
{
    if (lo == 0xFF && hi == 0xFF) return 0;    /* erased user row: no correction */
    return (int16_t)((uint16_t)lo | ((uint16_t)hi << 8));
}
