/* Minimal polled TWI0 master, 100 kHz. External pull-ups on the board. */
#include "board.h"
#include "twi.h"

#define TWI_BAUD ((F_CPU / (2UL * 100000UL)) - 5)   /* rise time ignored */
#define TIMEOUT  2000

static uint8_t wait_flag(uint8_t mask)
{
    uint16_t t = TIMEOUT;
    while (!(TWI0.MSTATUS & mask)) if (!--t) return 0;
    return 1;
}

void twi_init(void)
{
    TWI0.MBAUD = (uint8_t)TWI_BAUD;
    TWI0.MCTRLA = TWI_ENABLE_bm;
    TWI0.MSTATUS = TWI_BUSSTATE_IDLE_gc;
}

void twi_off(void) { TWI0.MCTRLA = 0; }

static uint8_t start(uint8_t addr_rw)
{
    TWI0.MADDR = addr_rw;
    if (!wait_flag(TWI_WIF_bm | TWI_RIF_bm)) return 0;
    if (TWI0.MSTATUS & (TWI_RXACK_bm | TWI_ARBLOST_bm | TWI_BUSERR_bm)) return 0;
    return 1;
}

static uint8_t send(uint8_t b)
{
    TWI0.MDATA = b;
    if (!wait_flag(TWI_WIF_bm)) return 0;
    return !(TWI0.MSTATUS & TWI_RXACK_bm);
}

static void stop(void) { TWI0.MCTRLB = TWI_MCMD_STOP_gc; }

uint8_t twi_write_reg(uint8_t addr, uint8_t reg, uint8_t val)
{
    uint8_t ok = start((uint8_t)(addr << 1)) && send(reg) && send(val);
    stop();
    return ok;
}

uint8_t twi_read_regs(uint8_t addr, uint8_t reg, uint8_t *buf, uint8_t n)
{
    if (!(start((uint8_t)(addr << 1)) && send(reg))) { stop(); return 0; }
    if (!start((uint8_t)(addr << 1) | 1)) { stop(); return 0; }   /* repeated start */
    for (uint8_t i = 0; i < n; i++) {
        if (i) TWI0.MCTRLB = TWI_MCMD_RECVTRANS_gc;                /* ACK, read next */
        if (!wait_flag(TWI_RIF_bm)) { stop(); return 0; }
        buf[i] = TWI0.MDATA;
    }
    TWI0.MCTRLB = TWI_ACKACT_bm | TWI_MCMD_STOP_gc;                 /* NACK last byte + STOP */
    return 1;
}
