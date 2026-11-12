#!/usr/bin/env bash
# Store the crystal correction in the user row (survives chip erase and re-flashing).
#   ./set-calibration.sh <ppm> [port]    e.g. ./set-calibration.sh +12.3
# Measuring: build with  EXTRA_CFLAGS="-DCAL_OUT=1" ./build.sh firmware , flash, and measure the
# period T of the square wave on the PA2 test pad (nominal 2.000000 s) with a frequency counter.
#   ppm = (T / 2 - 1) * 1e6     (positive: crystal slow, the watch adds time)
# Resolution 0.1 ppm, range +-3276.7 ppm. Then re-flash the normal build.
set -euo pipefail
PPM="${1:?usage: $0 <ppm> [port]}"
PORT="${2:-/dev/ttyUSB0}"
read -r LO HI < <(python3 -I -c '
import sys
v = round(float(sys.argv[1]) * 10)
if not -32767 <= v <= 32767: sys.exit("ppm out of range")
v &= 0xFFFF
print(hex(v & 0xFF), hex(v >> 8))' "$PPM")
echo "Writing correction $PPM ppm as user row bytes $LO $HI"
avrdude -c serialupdi -p t3217 -P "$PORT" -b 115200 -U usersig:w:$LO,$HI:m
