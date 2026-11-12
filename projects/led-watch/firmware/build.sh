#!/usr/bin/env bash
# Build the LED watch firmware for the ATtiny3217 and run the host unit tests.
#   ./build.sh            tests + firmware (build/led-watch.hex)
#   ./build.sh firmware   firmware only
#   ./build.sh test       host tests only
#   MCU=attiny1617 ./build.sh firmware   (pin-compatible 16 KB fallback)
#   EXTRA_CFLAGS="-DCAL_OUT=1" ./build.sh firmware   (crystal calibration build)
set -euo pipefail
cd "$(dirname "$0")"
MCU="${MCU:-attiny3217}"   # MCU=attiny1617 ./build.sh firmware for the 16 KB fallback
OUT=build
mkdir -p "$OUT"
what="${1:-all}"

PURE="src/core.c src/led_map.c src/timekeep.c src/battery.c src/clockface.c src/ui.c src/tilt.c"
HW="src/main.c src/twi.c src/lis2dh12.c"

if [ -f ../PINMAP.md ]; then python3 -I tools/gen_led_table.py --check; else echo "note: ../PINMAP.md not present (not merged yet), led_table.h not re-checked"; fi

if [ "$what" = all ] || [ "$what" = test ]; then
  gcc -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined \
      -Isrc $PURE test/test_main.c -o "$OUT/host-tests"
  "$OUT/host-tests"
fi

if [ "$what" = all ] || [ "$what" = firmware ]; then
  avr-gcc -mmcu=$MCU -std=gnu11 -Os -Wall -Wextra -Werror \
      -ffunction-sections -fdata-sections -Wl,--gc-sections \
      ${EXTRA_CFLAGS:-} -Isrc $PURE $HW -o "$OUT/led-watch.elf"
  avr-objcopy -O ihex -j .text -j .rodata -j .data "$OUT/led-watch.elf" "$OUT/led-watch.hex"
  avr-objcopy -O binary -j .fuse "$OUT/led-watch.elf" "$OUT/fuses.bin"
  avr-size -A "$OUT/led-watch.elf" | grep -E '^\.(text|data|bss|rodata|fuse) '
  echo "fuses (WDTCFG BODCFG OSCCFG - TCD0CFG SYSCFG0 SYSCFG1 APPEND BOOTEND):" $(od -An -tx1 "$OUT/fuses.bin")
fi
