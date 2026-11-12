#ifndef TWI_H
#define TWI_H
#include <stdint.h>
void twi_init(void);
void twi_off(void);
/* Return 1 on success (all bytes ACKed). */
uint8_t twi_write_reg(uint8_t addr, uint8_t reg, uint8_t val);
uint8_t twi_read_regs(uint8_t addr, uint8_t reg, uint8_t *buf, uint8_t n);
#endif
