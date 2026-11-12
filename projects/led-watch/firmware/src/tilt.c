#include "tilt.h"

#define MG_PER_COUNT 16
#define Z_MIN  (600 / MG_PER_COUNT)   /* 37 */
#define XY_MAX (500 / MG_PER_COUNT)   /* 31 */

static uint8_t absval(int8_t v) { return (uint8_t)(v < 0 ? -(int16_t)v : v); }

uint8_t tilt_face_up(int8_t x, int8_t y, int8_t z)
{
    return z >= Z_MIN && absval(x) <= XY_MAX && absval(y) <= XY_MAX;
}
