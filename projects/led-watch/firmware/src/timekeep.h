/* 12-hour clock with software drift correction. Pure C, host-testable. */
#ifndef TIMEKEEP_H
#define TIMEKEEP_H
#include <stdint.h>

/* One second = 1e6 ppm; the correction is in units of 0.1 ppm. */
#define CAL_ONE_SECOND 10000000L

typedef struct {
    uint8_t hour;     /* 0..11 (0 is shown at 12 o'clock) */
    uint8_t minute;   /* 0..59 */
    uint8_t second;   /* 0..59 */
    int16_t cal_x10;  /* +: crystal slow, add time; -: crystal fast, drop time. 0.1 ppm units */
    int32_t cal_acc;  /* correction accumulator */
} clock_t_;

void clock_init(clock_t_ *c, int16_t cal_x10);
/* Called once per crystal second (from the 1 Hz PIT). Applies the correction. */
void clock_tick(clock_t_ *c);
/* Advance the time by n seconds, with roll-over (no correction). */
void clock_add_seconds(clock_t_ *c, uint8_t n);
/* Time setting: step hour / minute; stepping the minute zeroes the seconds. */
void clock_step_hour(clock_t_ *c);
void clock_step_minute(clock_t_ *c);

/* Decode the 2 calibration bytes stored in the user row (little-endian int16, 0xFFFF = unset). */
int16_t clock_cal_from_bytes(uint8_t lo, uint8_t hi);

#endif
