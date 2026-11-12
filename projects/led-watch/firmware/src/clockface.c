#include "clockface.h"
#include "led_map.h"

#define SECONDS_TICKS 1

uint8_t clockface_frame(uint8_t hour, uint8_t minute, uint8_t second,
                        uint8_t flags, uint8_t on_ticks, uint8_t slots[FRAME_TICKS])
{
    uint8_t i = 0, n;
    if (on_ticks > 7) on_ticks = 7;            /* 7 + 7 + 1 <= FRAME_TICKS */

    if (!(flags & FACE_HIDE_HOUR))
        for (n = 0; n < on_ticks; n++) slots[i++] = led_hour(hour);
    if (!(flags & FACE_HIDE_MINUTE))
        for (n = 0; n < on_ticks; n++) slots[i++] = led_minute(minute);
    /* seconds dot, unless it sits on the minute LED (already lit or deliberately hidden) */
    if ((flags & FACE_SHOW_SECONDS) && second % 60 != minute % 60)
        for (n = 0; n < SECONDS_TICKS; n++) slots[i++] = led_minute(second);

    uint8_t lit = i;
    while (i < FRAME_TICKS) slots[i++] = LED_NONE;
    return lit;
}
