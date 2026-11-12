/* Button / tilt state machine. Pure C, host-testable. Call ui_step() every UI_STEP_MS while awake. */
#ifndef UI_H
#define UI_H
#include <stdint.h>
#include "timekeep.h"

#define UI_STEP_MS        10
#define UI_SHOW_MS      5000   /* time shown after a press or tilt */
#define UI_SET_HOLD_MS  2000   /* hold A+B this long to enter set mode */
#define UI_SET_IDLE_MS  5000   /* set mode saves and exits after this much idle time */
#define UI_FIRST_SET_MS 60000  /* after power-up, set mode waits longer */
#define UI_AFTER_SET_MS 2000   /* time shown after leaving set mode */
#define UI_LOWBAT_MS    1000
#define UI_REPEAT_DELAY_MS 600 /* hold B in set mode: auto-repeat minutes */
#define UI_REPEAT_MS     150
#define UI_WAKE_GRACE    5     /* steps to stay awake after a pin wake, to debounce */

typedef enum { UI_SLEEP, UI_SHOW, UI_SET, UI_LOWBAT } ui_state_t;
typedef enum { DISPLAY_OFF, DISPLAY_TIME, DISPLAY_LOWBAT } ui_display_t;

typedef struct {
    uint8_t a, b;          /* raw button levels: 1 = pressed */
    uint8_t tilt;          /* 1 = a qualified wrist-tilt happened since the last step */
    uint8_t battery_ok;    /* 1 = battery above VBAT_EMPTY_MV */
} ui_in_t;

typedef struct {
    ui_state_t state;
    uint16_t timer_ms;     /* time left in SHOW / LOWBAT; idle time in SET */
    uint16_t set_limit_ms; /* idle limit for the current SET session */
    uint16_t both_ms;      /* A+B held */
    uint16_t repeat_ms;    /* B held in SET */
    uint16_t blink_ms;
    uint8_t deb_a, deb_b;  /* debounce integrators */
    uint8_t a, b;          /* debounced levels */
    uint8_t wait_release;  /* in SET: ignore buttons until both are released */
    uint8_t grace;         /* steps left before sleeping after a pin wake */
} ui_t;

void ui_init(ui_t *u, uint8_t time_unset);
void ui_poke(ui_t *u);                     /* a wake interrupt fired: stay awake to debounce */
void ui_step(ui_t *u, const ui_in_t *in, clock_t_ *clk);
uint8_t ui_awake(const ui_t *u);
/* Call just before sleeping: forget held-button state so the next press is seen as a new press. */
void ui_sleep_reset(ui_t *u);
ui_display_t ui_display(const ui_t *u);
uint8_t ui_face_flags(const ui_t *u, uint8_t show_seconds);  /* FACE_* flags */

#endif
