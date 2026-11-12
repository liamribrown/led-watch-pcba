/* Battery voltage and LED duty compensation. Pure C, host-testable. */
#ifndef BATTERY_H
#define BATTERY_H
#include <stdint.h>

#define VBAT_EMPTY_MV   2400  /* below this the LEDs stay off (brown-out risk) */
#define VBAT_FRESH_MV   3000

/* VDD in mV from a 10-bit ADC reading of the internal 1.1 V reference with VDD as reference. */
uint16_t battery_mv_from_adc(uint16_t raw);
/* Scan ticks (out of FRAME_TICKS) for a hand LED: 4 at >= 3.0 V, rising to 7 at <= 2.6 V. */
uint8_t battery_on_ticks(uint16_t mv);

#endif
