/* LED analogue watch firmware, ATtiny3217.
 *
 * Asleep (power-down): only the RTC PIT runs, waking the CPU once a second to count time.
 * Awake: TCB0 ticks at 4 kHz and scans one LED per tick (charlieplex), and the UI state
 * machine runs every 10 ms. Wakes on button A or LIS2DH12 INT1 (low level, see wake_arm()).
 */
#include "board.h"
#include <avr/interrupt.h>
#include <avr/sleep.h>
#include <avr/cpufunc.h>
#include <util/atomic.h>

#include "core.h"
#include "tilt.h"
#include "twi.h"
#include "lis2dh12.h"

#ifndef CAL_OUT
#define CAL_OUT 0           /* 1: toggle PA2 every crystal second (0.5 Hz) to measure the crystal */
#endif

/* Fuses: BOD 1.8 V while awake, off in sleep (007: continuous BOD in sleep costs ~20 uA).
 * SYSCFG0 stays at the factory default, which keeps PA0 as UPDI: never change it. */
FUSES = {
    .WDTCFG  = FUSE_WDTCFG_DEFAULT,
    .BODCFG  = BOD_LVL_BODLEVEL0_gc | BOD_ACTIVE_ENABLED_gc | BOD_SLEEP_DIS_gc,
    .OSCCFG  = FUSE_OSCCFG_DEFAULT,
    .TCD0CFG = FUSE_TCD0CFG_DEFAULT,
    .SYSCFG0 = FUSE_SYSCFG0_DEFAULT,
    .SYSCFG1 = FUSE_SYSCFG1_DEFAULT,
    .APPEND  = FUSE_APPEND_DEFAULT,
    .BOOTEND = FUSE_BOOTEND_DEFAULT,
};

/* ---- shared with ISRs ---- */
static core_t core;                     /* shared logic (core.c); the scan ISR reads its frames */
static volatile uint8_t pending_secs;   /* PIT seconds not yet applied to the clock */
static volatile uint8_t wake_pins;      /* wake input went low (bit0: any, bit1: accelerometer) */
static volatile uint8_t ticks;          /* 4 kHz ticks, for the 10 ms UI step */
static uint8_t have_acc;                /* LIS2DH12 answered at start-up */

/* ---- charlieplex output ----
 * Rule from the hardware review (007): between LEDs, make every line an input first, then set the
 * next pair. The all-low step before that drains stray charge on the lines (ghosting mitigation). */
static inline void lines_float(void)
{
    VPORTA.DIR &= (uint8_t)~LED_PA_MASK;  VPORTB.DIR &= (uint8_t)~LED_PB_MASK;
    VPORTA.OUT &= (uint8_t)~LED_PA_MASK;  VPORTB.OUT &= (uint8_t)~LED_PB_MASK;
}

static inline void lines_drain(void)
{
    VPORTA.OUT &= (uint8_t)~LED_PA_MASK;  VPORTB.OUT &= (uint8_t)~LED_PB_MASK;
    VPORTA.DIR |= LED_PA_MASK;            VPORTB.DIR |= LED_PB_MASK;
}

ISR(TCB0_INT_vect)
{
    TCB0.INTFLAGS = TCB_CAPT_bm;
    uint8_t led = core_next_led(&core);
    ticks++;

    lines_drain();
    lines_float();
    uint16_t dir, out;
    core_tick_lines(led, &dir, &out);          /* cathode low, anode high */
    VPORTA.OUT |= core_pa_bits(out);  VPORTB.OUT |= core_pb_bits(out);
    VPORTA.DIR |= core_pa_bits(dir);  VPORTB.DIR |= core_pb_bits(dir);
}

ISR(RTC_PIT_vect)
{
    RTC.PITINTFLAGS = RTC_PI_bm;
    if (pending_secs < 255) pending_secs++;
#if CAL_OUT
    VPORTA.IN = CALPAD_bm;                 /* writing IN toggles the output */
#endif
}

/* Level-sensed wake: the interrupt request stays up while a pin is low, so switch the sensing off
 * first (which also drops the request), then clear the flags. */
ISR(PORTC_PORT_vect)
{
    uint8_t f = PORTC.INTFLAGS;
    if (f & ACC_INT_bm) { PORTC.PIN0CTRL = PORT_PULLUPEN_bm; wake_pins |= 2; }
    if (f & BTN_A_bm)     PORTC.PIN2CTRL = PORT_PULLUPEN_bm;
    PORTC.INTFLAGS = f;
    wake_pins |= 1;
}

/* ---- setup ---- */
static void pins_init(void)
{
    /* Everything off by default: input buffers disabled to avoid leakage in sleep (007).
     * PB0/PB1 (TWI) are left alone until we know whether the accelerometer is fitted. */
    for (uint8_t i = 0; i < 8; i++) {
        (&PORTA.PIN0CTRL)[i] = PORT_ISC_INPUT_DISABLE_gc;
        (&PORTB.PIN0CTRL)[i] = PORT_ISC_INPUT_DISABLE_gc;
        (&PORTC.PIN0CTRL)[i] = PORT_ISC_INPUT_DISABLE_gc;
    }
    PORTB.PIN0CTRL = 0;
    PORTB.PIN1CTRL = 0;
    /* PA0 is UPDI while the SYSCFG0 fuse says so; its PINCTRL is ignored. */
    PORTC.PIN2CTRL = PORT_PULLUPEN_bm;      /* button A */
    PORTC.PIN3CTRL = PORT_PULLUPEN_bm;      /* button B */
    lines_float();
#if CAL_OUT
    VPORTA.DIR |= CALPAD_bm;
#endif
}

/* Arm low-level wake on button A and INT1 when they are currently high. Button B doesn't wake the chip:
 * A+B set-mode entry starts with A, and B is read whenever the chip is awake. A pin that is already low (a held
 * or stuck button, a latched INT1) is left unarmed: it would wake the chip again at once. The next
 * PIT wake (within 1 s) re-arms it once it has been released. */
static void wake_arm(void)
{
    uint8_t in = PORTC.IN;
    uint8_t flags = BTN_A_bm | (have_acc ? ACC_INT_bm : 0);
    PORTC.INTFLAGS = flags;
    if (have_acc && (in & ACC_INT_bm)) PORTC.PIN0CTRL = PORT_PULLUPEN_bm | PORT_ISC_LEVEL_gc;
    if (in & BTN_A_bm)                 PORTC.PIN2CTRL = PORT_PULLUPEN_bm | PORT_ISC_LEVEL_gc;
}

static void rtc_init(void)
{
    _PROTECTED_WRITE(CLKCTRL.XOSC32KCTRLA, CLKCTRL_CSUT_1K_gc | CLKCTRL_ENABLE_bm);
    while (RTC.STATUS) ;
    RTC.CLKSEL = RTC_CLKSEL_TOSC32K_gc;
    while (RTC.PITSTATUS) ;
    RTC.PITINTCTRL = RTC_PI_bm;
    RTC.PITCTRLA = RTC_PERIOD_CYC32768_gc | RTC_PITEN_bm;   /* 1 Hz */
}

static void scan_start(void)
{
    TCB0.CCMP = (uint16_t)(F_CPU / TICK_HZ - 1);
    TCB0.CTRLB = TCB_CNTMODE_INT_gc;
    TCB0.INTCTRL = TCB_CAPT_bm;
    TCB0.CTRLA = TCB_CLKSEL_CLKDIV1_gc | TCB_ENABLE_bm;
}

static void scan_stop(void)
{
    TCB0.CTRLA = 0;
    TCB0.INTFLAGS = TCB_CAPT_bm;
    lines_float();
}

static uint16_t battery_read_mv(void)
{
    VREF.CTRLA = VREF_ADC0REFSEL_1V1_gc;
    ADC0.CTRLC = ADC_SAMPCAP_bm | ADC_REFSEL_VDDREF_gc | ADC_PRESC_DIV4_gc;
    ADC0.CTRLD = ADC_INITDLY_DLY64_gc;
    ADC0.MUXPOS = ADC_MUXPOS_INTREF_gc;
    ADC0.CTRLA = ADC_ENABLE_bm;
    uint16_t raw = 0;
    for (uint8_t i = 0; i < 2; i++) {          /* first conversion discarded */
        ADC0.COMMAND = ADC_STCONV_bm;
        while (!(ADC0.INTFLAGS & ADC_RESRDY_bm)) ;
        raw = ADC0.RES;
    }
    ADC0.CTRLA = 0;
    return battery_mv_from_adc(raw);
}

/* ---- main ---- */
static void apply_pending_seconds(void)
{
    uint8_t n;
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { n = pending_secs; pending_secs = 0; }
    core_apply_seconds(&core, n);
}

static void go_to_sleep(void)
{
    scan_stop();
    ui_sleep_reset(&core.ui);                       /* a button still held now counts as a new press later */
    wake_arm();
    set_sleep_mode(SLEEP_MODE_PWR_DOWN);
    cli();
    if (!wake_pins && !pending_secs) {
        sleep_enable();
        sei();
        sleep_cpu();
        sleep_disable();
    }
    sei();
}

/* Read the accelerometer; clears its latched INT1. Returns 1 if the wrist is face up. */
static uint8_t acc_check(void)
{
    int8_t x, y, z;
    return lis_read(&x, &y, &z) && tilt_face_up(x, y, z);
}

int main(void)
{
    pins_init();
    rtc_init();
    core_init(&core, clock_cal_from_bytes(USERROW.USERROW0, USERROW.USERROW1));

    twi_init();
    have_acc = lis_init();
    if (have_acc) {
        PORTC.PIN0CTRL = PORT_PULLUPEN_bm;    /* INT1 input */
        (void)acc_check();                    /* clear a latch left by motion during start-up */
    } else {
        twi_off();                            /* unfitted: no bus traffic, no leakage paths */
        PORTB.PIN0CTRL = PORT_ISC_INPUT_DISABLE_gc;
        PORTB.PIN1CTRL = PORT_ISC_INPUT_DISABLE_gc;
    }
    sei();

    uint8_t awake_before = 0;
    for (;;) {
        apply_pending_seconds();

        uint8_t tilt = 0, w;
        ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { w = wake_pins; wake_pins = 0; }
        /* A stuck-low INT1 (failed read, or it was low before it could be armed) is retried here:
         * every PIT wake gets another chance to read the sensor and release the latch. */
        if (have_acc && !(PORTC.IN & ACC_INT_bm)) w |= 2;
        if (w & 2) tilt = acc_check();
        core_wake_events(&core, w & 1, tilt);

        if (core_idle(&core, tilt)) { awake_before = 0; go_to_sleep(); continue; }

        if (!awake_before) {                  /* just woke: measure the battery, start scanning */
            core_start_awake(&core, battery_read_mv());
            ticks = 0;
            scan_start();
            awake_before = 1;
        }

        set_sleep_mode(SLEEP_MODE_IDLE);       /* idle between scan ticks */
        while (ticks < TICKS_PER_STEP) sleep_mode();
        ticks = 0;

        core_step(&core, !(PORTC.IN & BTN_A_bm), !(PORTC.IN & BTN_B_bm), tilt);
    }
}
