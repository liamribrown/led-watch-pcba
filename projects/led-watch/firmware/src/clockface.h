/* Turns the time into one scan frame for the charlieplex ISR. Pure C, host-testable. */
#ifndef CLOCKFACE_H
#define CLOCKFACE_H
#include <stdint.h>

#define FRAME_TICKS 16   /* ticks per frame; 4 kHz tick -> 250 Hz frame */

#define FACE_HIDE_HOUR    0x01  /* blink phase: hour LED off */
#define FACE_HIDE_MINUTE  0x02
#define FACE_SHOW_SECONDS 0x04  /* dim seconds dot on the minute ring */

/* Fill slots[FRAME_TICKS] with LED indices (LED_NONE = all lines off for that tick).
 * on_ticks: ticks for each hand LED (from battery_on_ticks). Returns the number of lit ticks. */
uint8_t clockface_frame(uint8_t hour, uint8_t minute, uint8_t second,
                        uint8_t flags, uint8_t on_ticks, uint8_t slots[FRAME_TICKS]);

#endif
