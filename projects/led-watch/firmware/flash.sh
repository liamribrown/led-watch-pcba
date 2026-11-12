#!/usr/bin/env bash
# Flash the LED watch over UPDI with a USB-serial adapter (SerialUPDI: TX--[470R]--RX tied to UPDI).
#   ./flash.sh [port]        default /dev/ttyUSB0
# Writes flash and the BODCFG fuse only. SYSCFG0 (which keeps PA0 as UPDI) is never written.
# Only run with 000's OK and a board on the jig.
set -euo pipefail
cd "$(dirname "$0")"
PORT="${1:-/dev/ttyUSB0}"
[ -f build/led-watch.hex ] || { echo "No build: run ./build.sh first" >&2; exit 1; }
BODCFG=$(od -An -tx1 -j1 -N1 build/fuses.bin | tr -d ' ')
[ "$BODCFG" = "04" ] || { echo "Unexpected BODCFG 0x$BODCFG in build/fuses.bin" >&2; exit 1; }
[ -r "$PORT" ] && [ -w "$PORT" ] || { echo "Cannot open $PORT (missing, or no dialout permission; ask 000)" >&2; exit 1; }
avrdude -c serialupdi -p t3217 -P "$PORT" -b 115200 \
  -U flash:w:build/led-watch.hex:i \
  -U bodcfg:w:0x$BODCFG:m
