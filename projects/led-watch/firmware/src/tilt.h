/* Wrist-tilt qualification from an LIS2DH12 sample. Pure C, host-testable. */
#ifndef TILT_H
#define TILT_H
#include <stdint.h>

/* x, y, z: LIS2DH12 low-power-mode 8-bit samples (OUT_x_H), +-2 g range, 16 mg per count.
 * Face up and roughly level: z >= +0.6 g and |x|, |y| <= 0.5 g.
 * ASSUMPTION: the LIS2DH12 sits on the top (LED) side with its +Z out of the dial. */
uint8_t tilt_face_up(int8_t x, int8_t y, int8_t z);

#endif
