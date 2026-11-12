#!/usr/bin/env bash
# Build watch.wasm from the real firmware modules + sim.c. Needs clang-19 and wasm-ld-19 (apt: clang-19 lld-19).
set -euo pipefail
cd "$(dirname "$0")"
FW=../../led-watch/firmware/src
OUT="${1:-../public/watch.wasm}"
clang-19 --target=wasm32 -std=gnu11 -Os -Wall -Wextra -Werror -ffreestanding -fno-builtin -nostdlib \
  -fvisibility=hidden -I"$FW" \
  -Wl,--no-entry -Wl,--export-dynamic -Wl,--gc-sections -Wl,--strip-all -Wl,-z,stack-size=4096 \
  "$FW"/{ui,timekeep,clockface,led_map,tilt,battery,core}.c sim.c -o "$OUT"
ls -l "$OUT"
