/* LED numbering and the charlieplex wiring table (from the board, see led_table.h). Pure C, host-testable. */
#ifndef LED_MAP_H
#define LED_MAP_H
#include <stdint.h>

#define LED_LINES       9   /* charlieplex lines L0..L8 */
#define LED_COUNT      72   /* 9 * 8 */
#define LED_MINUTE_FIRST 0  /* minute ring: LED 0..59, LED 0 at 12 o'clock, clockwise */
#define LED_HOUR_FIRST  60  /* hour ring:   LED 60..71, LED 60 at 12 o'clock, clockwise */
#define LED_NONE     0xFF

/* LED index for minute 0..59 / hour 0..11 (hour may be 0..23; it is taken mod 12). */
uint8_t led_minute(uint8_t minute);
uint8_t led_hour(uint8_t hour);

/* Charlieplex lines for an LED: current flows from line *anode to line *cathode.
 * Returns 0 for an invalid LED index. */
uint8_t led_lines(uint8_t led, uint8_t *anode, uint8_t *cathode);

#endif
