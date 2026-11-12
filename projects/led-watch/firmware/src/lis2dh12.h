#ifndef LIS2DH12_H
#define LIS2DH12_H
#include <stdint.h>
/* Returns 1 if the chip answered WHO_AM_I and was configured for wake-on-motion. */
uint8_t lis_init(void);
/* Read and clear the interrupt latch, then read one sample. Returns 1 on success. */
uint8_t lis_read(int8_t *x, int8_t *y, int8_t *z);
#endif
