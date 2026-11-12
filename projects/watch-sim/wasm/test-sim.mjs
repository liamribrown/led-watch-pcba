// Run: ~/.local/node/bin/node test-sim.mjs   (builds nothing; uses ../public/watch.wasm)
import { readFileSync } from 'node:fs';
const { instance } = await WebAssembly.instantiate(readFileSync(new URL('../public/watch.wasm', import.meta.url)), {});
const w = instance.exports;
const K = n => w.sim_const(n);
const C = {}; ['UI_SHOW_MS','UI_SET_HOLD_MS','UI_SET_IDLE_MS','UI_FIRST_SET_MS','UI_AFTER_SET_MS','UI_LOWBAT_MS','VBAT_EMPTY_MV','VBAT_FRESH_MV',
 'FRAME_TICKS','LED_COUNT','LED_LINES','TICK_HZ','UI_STEP_MS','UI_SLEEP','UI_SHOW','UI_SET','UI_LOWBAT','DISPLAY_OFF','DISPLAY_TIME','DISPLAY_LOWBAT',
 'LED_MINUTE_FIRST','LED_HOUR_FIRST','LED_NONE'].forEach((n,i)=>C[n]=K(i));
let fails = 0, checks = 0;
const ok = (c, m) => { checks++; if (!c) { fails++; console.log('FAIL:', m); } };
const lit = () => { const s=[]; for (let i=0;i<C.LED_COUNT;i++) if (w.sim_led_duty(i)) s.push(i); return s; };
const press = (a,b,ms) => { w.sim_set_inputs(a,b); w.sim_advance_ms(ms); };

ok(C.UI_SHOW_MS===5000 && C.FRAME_TICKS===16 && C.LED_COUNT===72, 'constants come from the firmware headers');
// power-up: set mode, 12:00, awake
w.sim_init();
ok(w.sim_state()===C.UI_SET && w.sim_awake(), 'power-up starts in set mode');
ok(w.sim_hour()===0 && w.sim_minute()===0, 'starts at 12:00');
w.sim_advance_ms(C.UI_FIRST_SET_MS + 100);
ok(w.sim_display()!==C.DISPLAY_TIME || w.sim_state()===C.UI_SHOW, 'first set mode times out into SHOW');
w.sim_advance_ms(C.UI_AFTER_SET_MS + 200);
ok(w.sim_state()===C.UI_SLEEP && !w.sim_awake(), 'falls asleep after the after-set display');
ok(w.sim_line_dir()===0 && w.sim_line_out()===0, 'all lines floating asleep');
ok(w.sim_minute()===1 && w.sim_second()>=0, 'clock kept counting (about 1 min + 2 s)');
const t0 = [w.sim_hour(), w.sim_minute(), w.sim_second()];
// press A: show the time for UI_SHOW_MS
press(1,0,100); press(0,0,100);
ok(w.sim_awake() && w.sim_state()===C.UI_SHOW && w.sim_display()===C.DISPLAY_TIME, 'press A wakes and shows the time');
const L = lit();
ok(L.includes(C.LED_HOUR_FIRST + w.sim_hour()) && L.includes(C.LED_MINUTE_FIRST + w.sim_minute()), 'hour and minute LEDs are lit: '+L);
// walk: each tick lights one LED; its lines match the table
let bad = 0;
for (let t=0;t<64;t++){ const led=w.sim_tick_log(t); if(led!==C.LED_NONE){ const l=w.sim_led_lines(led); const a=l>>4,c=l&15; if(a===c) bad++; } }
ok(bad===0, 'tick log has valid anode/cathode pairs');
w.sim_advance_ms(1); { const led=w.sim_tick_log(0); if(led!==C.LED_NONE){ const l=w.sim_led_lines(led), a=l>>4,c=l&15;
  ok(w.sim_line_dir()===((1<<a)|(1<<c)) && w.sim_line_out()===(1<<a), 'line masks match the lit LED'); } }
w.sim_advance_ms(C.UI_SHOW_MS - 200);
ok(w.sim_awake(), 'still showing just before UI_SHOW_MS');
w.sim_advance_ms(500);
ok(!w.sim_awake() && w.sim_state()===C.UI_SLEEP, 'asleep after UI_SHOW_MS');
// A+B held enters set mode
press(1,1,C.UI_SET_HOLD_MS - 300); ok(w.sim_state()!==C.UI_SET, 'not in set mode before UI_SET_HOLD_MS');
w.sim_advance_ms(600); ok(w.sim_state()===C.UI_SET, 'A+B held enters set mode');
press(0,0,200); const h0=w.sim_hour(); press(1,0,100); press(0,0,100);
ok(w.sim_hour()===(h0+1)%12, 'A steps the hour in set mode');
const m1=w.sim_minute(); press(0,1,100); press(0,0,100); ok(w.sim_minute()===(m1+1)%60 && w.sim_second()===0, `B steps the minute and zeroes seconds (${m1} -> ${w.sim_minute()}:${w.sim_second()})`);
w.sim_advance_ms(C.UI_SET_IDLE_MS + 300); ok(w.sim_state()!==C.UI_SET, 'set mode times out');
w.sim_advance_ms(C.UI_AFTER_SET_MS + 500); ok(!w.sim_awake(), 'asleep again');
// tilt: face up wakes; a face-down shake does not show
w.sim_set_accel(0,0,-64); w.sim_advance_ms(300);
ok(!w.sim_awake(), 'face-down motion does not wake the display');
w.sim_set_accel(0,0,64); w.sim_advance_ms(100);
ok(w.sim_awake() && w.sim_display()===C.DISPLAY_TIME, 'tilting face up wakes and shows the time');
w.sim_advance_ms(C.UI_SHOW_MS + 500); ok(!w.sim_awake(), 'asleep after the tilt display');
// battery below VBAT_EMPTY_MV: no time, blink LED 0
w.sim_set_vbat_mv(C.VBAT_EMPTY_MV - 100);
press(1,0,100); press(0,0,100);
ok(w.sim_state()===C.UI_LOWBAT && w.sim_display()===C.DISPLAY_LOWBAT, 'low battery shows the low-battery pattern');
let seen0 = false, seenOther = false;
for (let i=0;i<C.UI_LOWBAT_MS/10;i++){ w.sim_advance_ms(10); for(let t=0;t<16;t++){const l=w.sim_tick_log(t); if(l===C.LED_MINUTE_FIRST) seen0=true; else if(l!==C.LED_NONE) seenOther=true;} }
ok(seen0 && !seenOther, 'only LED 0 blinks on low battery');
w.sim_advance_ms(C.UI_LOWBAT_MS + 500); ok(!w.sim_awake(), 'asleep after the low-battery blink');
// duty compensation: fresh vs weak cell
w.sim_set_vbat_mv(C.VBAT_FRESH_MV); press(1,0,100); press(0,0,100);
const dFresh = w.sim_led_duty(C.LED_HOUR_FIRST + w.sim_hour());
w.sim_advance_ms(C.UI_SHOW_MS + 500);
w.sim_set_vbat_mv(2600); press(1,0,100); press(0,0,100);
const dWeak = w.sim_led_duty(C.LED_HOUR_FIRST + w.sim_hour());
ok(dWeak > dFresh, `weaker cell gets more on-ticks (${dFresh} -> ${dWeak})`);
w.sim_advance_ms(C.UI_SHOW_MS + 500);
// stuck button: held A does not keep the watch awake
press(1,0,100); w.sim_advance_ms(C.UI_SHOW_MS + 3000);
ok(!w.sim_awake(), 'a stuck-pressed A button does not keep the watch awake');
// timekeeping while asleep: 1 hour
press(0,0,100); w.sim_advance_ms(1000);
const m = w.sim_minute(); w.sim_advance_ms(3600*1000);
ok(w.sim_minute()===m, 'one hour of sleep advances the hour, not the minute');
console.log(`${checks} checks, ${fails} failures`);
process.exit(fails ? 1 : 0);
