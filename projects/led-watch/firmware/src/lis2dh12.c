/* LIS2DH12: low-power mode, 10 Hz, motion interrupt on INT1 (active low, latched).
 * Register values from the LIS2DH12 datasheet; 007 to double-check. */
#include "board.h"
#include "twi.h"
#include "lis2dh12.h"

#define WHO_AM_I      0x0F
#define WHO_AM_I_VAL  0x33
#define CTRL_REG1     0x20
#define CTRL_REG2     0x21
#define CTRL_REG3     0x22
#define CTRL_REG4     0x23
#define CTRL_REG5     0x24
#define CTRL_REG6     0x25
#define REFERENCE     0x26
#define OUT_X_L       0x28
#define INT1_CFG      0x30
#define INT1_SRC      0x31
#define INT1_THS      0x32
#define INT1_DURATION 0x33
#define AUTO_INC      0x80

uint8_t lis_init(void)
{
    uint8_t id = 0, dummy;
    if (!twi_read_regs(ACC_I2C_ADDR, WHO_AM_I, &id, 1) || id != WHO_AM_I_VAL) return 0;
    uint8_t ok = 1;
    ok &= twi_write_reg(ACC_I2C_ADDR, CTRL_REG1, 0x2F);     /* ODR 10 Hz, low-power, X/Y/Z on */
    ok &= twi_write_reg(ACC_I2C_ADDR, CTRL_REG2, 0x01);     /* high-pass filter on the INT1 path */
    ok &= twi_write_reg(ACC_I2C_ADDR, CTRL_REG3, 0x40);     /* IA1 interrupt on INT1 */
    ok &= twi_write_reg(ACC_I2C_ADDR, CTRL_REG4, 0x00);     /* +-2 g */
    ok &= twi_write_reg(ACC_I2C_ADDR, CTRL_REG5, 0x08);     /* latch INT1 until INT1_SRC is read */
    ok &= twi_write_reg(ACC_I2C_ADDR, CTRL_REG6, 0x02);     /* INT pins active low */
    ok &= twi_write_reg(ACC_I2C_ADDR, INT1_THS, 0x10);      /* 16 * 16 mg = 256 mg */
    ok &= twi_write_reg(ACC_I2C_ADDR, INT1_DURATION, 0x01); /* 1 sample (100 ms) */
    ok &= twi_read_regs(ACC_I2C_ADDR, REFERENCE, &dummy, 1);/* reset the HP filter */
    ok &= twi_write_reg(ACC_I2C_ADDR, INT1_CFG, 0x2A);      /* OR of X/Y/Z high events */
    return ok;
}

uint8_t lis_read(int8_t *x, int8_t *y, int8_t *z)
{
    uint8_t src, d[6];
    if (!twi_read_regs(ACC_I2C_ADDR, INT1_SRC, &src, 1)) return 0;
    if (!twi_read_regs(ACC_I2C_ADDR, OUT_X_L | AUTO_INC, d, 6)) return 0;
    *x = (int8_t)d[1]; *y = (int8_t)d[3]; *z = (int8_t)d[5];   /* low-power mode: 8 bits in OUT_x_H */
    return 1;
}
