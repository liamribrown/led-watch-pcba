#include "led_map.h"
#include "led_table.h"   /* generated from the board's PINMAP.md by tools/gen_led_table.py */

uint8_t led_minute(uint8_t minute) { return (uint8_t)(LED_MINUTE_FIRST + minute % 60); }
uint8_t led_hour(uint8_t hour)     { return (uint8_t)(LED_HOUR_FIRST + hour % 12); }

uint8_t led_lines(uint8_t led, uint8_t *anode, uint8_t *cathode)
{
    if (led >= LED_COUNT) return 0;
    uint8_t v = led_table[led];
    *anode = v >> 4;
    *cathode = v & 0x0F;
    return 1;
}
