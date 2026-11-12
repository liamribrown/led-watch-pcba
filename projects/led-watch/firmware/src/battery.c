#include "battery.h"

#define VREF_MV 1100UL

uint16_t battery_mv_from_adc(uint16_t raw)
{
    if (raw == 0) return 0xFFFF;               /* impossible reading: report "very high" */
    uint32_t mv = (VREF_MV * 1023UL + raw / 2) / raw;
    return mv > 0xFFFE ? 0xFFFE : (uint16_t)mv;
}

uint8_t battery_on_ticks(uint16_t mv)
{
    if (mv >= VBAT_FRESH_MV) return 4;
    if (mv <= 2600) return 7;
    /* 3 extra ticks over 400 mV, rounded */
    return (uint8_t)(4 + ((VBAT_FRESH_MV - mv) * 3 + 200) / 400);
}
