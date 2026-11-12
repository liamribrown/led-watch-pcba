#!/usr/bin/env python3
"""Generate the LED watch KiCad 9 project: schematic, PCB and project libraries.

    python3 projects/led-watch/tools/generate.py

Writes led-watch.kicad_sch / .kicad_pcb / .kicad_pro, led-watch.kicad_sym,
led-watch.pretty/ and the project library tables next to it. Re-running it
overwrites them, so change the design here (or in design.py), not in KiCad,
until the layout is frozen.

Board: 38 mm round, 4 layers. Top: 60 minute LEDs (r = 17.3 mm), 12 hour LEDs
(r = 9.6 mm) and all electronics inside r < 8.4 mm. In2: nine concentric rings,
one per charlieplex line. In1: GND plane + nine spokes from the rings to the
line resistors. Bottom: CR2032 clip, two side buttons, programming pads.
"""
import math
import os
import heapq
import uuid
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import design as D  # noqa: E402

PROJ = os.path.dirname(HERE)
NAME = "led-watch"
KS = "/usr/share/kicad/symbols"
KF = "/usr/share/kicad/footprints"
NS = uuid.UUID("6f0d3c1e-6a2b-4b8e-9a51-3d2f0c7e9a11")


def U(*key):
    """Deterministic UUIDs so regenerating gives a stable diff."""
    return str(uuid.uuid5(NS, "/".join(map(str, key))))


# ============================================================ geometry constants (mm)
CX, CY = 100.0, 100.0
R_BOARD = 19.0
R_MIN_LED = 17.3      # minute LED centres
R_ARC_OUT = 18.2      # minute anode arcs
R_HOUR_LED = 9.6      # hour LED centres
R_ARC_IN = 8.65       # hour anode arcs
R_RING0, RING_PITCH = 10.6, 0.6   # line k ring on In2 at 10.6 + 0.6 k
R_SPOKE_IN = 7.7      # inner end of the In1 spokes (via up to F.Cu)
R_RES = 6.55          # line resistors
HOUR_VIA_OFF = 0.45   # hour cathode vias sit 0.45 mm clockwise of the sector centre
TRACK = 0.15
TRACK_R = 0.2         # router track width
CLEAR = 0.12
VIA_D, VIA_DRILL = 0.5, 0.3


def ring_r(k):
    return R_RING0 + RING_PITCH * k


def polar(r, deg):
    """Clock angle in degrees (0 = 12 o'clock, clockwise) -> board mm."""
    a = math.radians(deg)
    return (CX + r * math.sin(a), CY - r * math.cos(a))


def clock_deg(x, y):
    return math.degrees(math.atan2(x - CX, -(y - CY))) % 360


# ============================================================ parts
def build_parts():
    """Return list of part dicts: ref, kind, lib_id, pins {pin: net}, extra."""
    mins, hours, anodes, blocks = D.assign_leds()
    parts = []

    def add(ref, kind, lib_id, pins, **kw):
        d = dict(ref=ref, kind=kind, lib_id=lib_id, pins=pins, **D.P[kind])
        d.update(kw)
        parts.append(d)
        return d

    add("U1", "MCU", "MCU_Microchip_ATtiny:ATtiny3217-M", dict(D.MCU_PINS))
    add("U2", "ACC", "led-watch:LIS2DH12", dict(D.ACC_PINS))
    add("Y1", "XTAL", "Device:Crystal", {"1": "XT1", "2": "XT2"})
    add("C5", "C6p8", "Device:C", {"1": "XT1", "2": "GND"})
    add("C6", "C6p8", "Device:C", {"1": "XT2", "2": "GND"})
    add("Q1", "FET", "Transistor_FET:AO3401A", {"1": "GND", "2": "VDD", "3": "VBAT"})
    add("BT1", "BAT", "Device:Battery_Cell", {"1": "VBAT", "2": "GND"})
    add("C1", "C100n", "Device:C", {"1": "VDD", "2": "GND"})
    add("C3", "C22u", "Device:C", {"1": "VDD", "2": "GND"})
    add("C4", "C100n", "Device:C", {"1": "VDD", "2": "GND"})
    add("R10", "R4k7", "Device:R", {"1": "VDD", "2": "SCL"})
    add("R11", "R4k7", "Device:R", {"1": "VDD", "2": "SDA"})
    add("SW1", "SW", "led-watch:SW_B3U", {"1": "SW_A_K", "2": "GND", "3": "GND"})
    add("SW2", "SW", "led-watch:SW_B3U", {"1": "SW_B_K", "2": "GND", "3": "GND"})
    # 007 review #12: 1k series resistor + footprint for an ESD diode at each button (frame to GND)
    add("R12", "R1k", "Device:R", {"1": "SW_A_K", "2": "SW_A"})
    add("R13", "R1k", "Device:R", {"1": "SW_B_K", "2": "SW_B"})
    add("D73", "TVS", "Device:D_TVS", {"1": "SW_A_K", "2": "GND"}, dnp=True)
    add("D74", "TVS", "Device:D_TVS", {"1": "SW_B_K", "2": "GND"}, dnp=True)
    add("C7", "C100n", "Device:C", {"1": "SW_A", "2": "GND"})
    add("C8", "C100n", "Device:C", {"1": "SW_B", "2": "GND"})
    # no VDD pad (007 review #1): program from the cell, SerialUPDI needs only UPDI + GND
    for i, net in enumerate(["UPDI", "GND", "TX", "RTC"]):
        add(f"TP{i+1}", "TP", "Connector:TestPoint", {"1": net}, value=net)
    for k in range(D.N_LINES):
        add(f"R{k+1}", "R100", "Device:R", {"1": f"L{k}_M", "2": f"L{k}"})
    for m in range(60):
        a, c = mins[m]
        add(f"D{m+1}", "LED_M", "Device:LED", {"1": f"L{c}", "2": f"L{a}"}, minute=m)
    for h in range(12):
        a, c = hours[h]
        add(f"D{61+h}", "LED_H", "Device:LED", {"1": f"L{c}", "2": f"L{a}"}, hour=h)
    return parts, (mins, hours, anodes, blocks)


# ============================================================ libraries
def sexp_block(t, start):
    d = 0
    for j in range(start, len(t)):
        if t[j] == "(":
            d += 1
        elif t[j] == ")":
            d -= 1
            if d == 0:
                return t[start:j + 1]
    raise ValueError("unbalanced")


def lib_symbol(lib, name):
    t = open(f"{KS}/{lib}.kicad_sym").read()
    i = t.find(f'(symbol "{name}"\n')
    s = sexp_block(t, i)
    if "(extends" in s:   # flatten a derived symbol onto its base
        base = s.split('(extends "')[1].split('"')[0]
        b = sexp_block(t, t.find(f'(symbol "{base}"\n'))
        b = b.replace(f'(symbol "{base}"', f'(symbol "{name}"', 1)
        b = b.replace(f'(symbol "{base}_', f'(symbol "{name}_')
        # the derived symbol's own properties win over the base's
        dprops = {}
        i = 0
        while True:
            i = s.find("(property ", i)
            if i < 0:
                break
            blk = sexp_block(s, i)
            dprops[blk.split('"')[1]] = blk
            i += len(blk)
        i = 0
        while True:
            i = b.find("(property ", i)
            if i < 0:
                break
            blk = sexp_block(b, i)
            key = blk.split('"')[1]
            if key in dprops:
                b = b[:i] + dprops.pop(key) + b[i + len(blk):]
            i += 1
        if dprops:   # properties only the derived symbol has
            j = b.find("(symbol ", 1)
            b = b[:j] + "\n".join(dprops.values()) + "\n" + b[j:]
        s = b
    return s.replace(f'(symbol "{name}"', f'(symbol "{lib}:{name}"', 1)


def make_symbol(name, ref, value, fp, pins, half_w, half_h, desc):
    """pins: list of (number, name, etype, side, slot, hidden); side in L/R/T/B."""
    out = [f'(symbol "{name}" (exclude_from_sim no) (in_bom yes) (on_board yes)',
           f'  (property "Reference" "{ref}" (at 0 {half_h + 2.54} 0) (effects (font (size 1.27 1.27))))',
           f'  (property "Value" "{value}" (at 0 {-half_h - 2.54} 0) (effects (font (size 1.27 1.27))))',
           f'  (property "Footprint" "{fp}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
           f'  (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
           f'  (property "Description" "{desc}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
           f'  (symbol "{name}_0_1" (rectangle (start {-half_w} {half_h}) (end {half_w} {-half_h})'
           f' (stroke (width 0.254) (type default)) (fill (type background))))',
           f'  (symbol "{name}_1_1"']
    for num, pname, et, side, slot, hidden in pins:
        if side == "L":
            x, y, a = -half_w - 2.54, half_h - 2.54 * (slot + 1), 0
        elif side == "R":
            x, y, a = half_w + 2.54, half_h - 2.54 * (slot + 1), 180
        elif side == "T":
            x, y, a = -half_w + 2.54 * (slot + 1), half_h + 2.54, 270
        else:
            x, y, a = -half_w + 2.54 * (slot + 1), -half_h - 2.54, 90
        hid = " (hide yes)" if hidden else ""
        out.append(f'    (pin {et} line (at {x:g} {y:g} {a}) (length 2.54){hid}'
                   f' (name "{pname}" (effects (font (size 1.27 1.27))))'
                   f' (number "{num}" (effects (font (size 1.27 1.27)))))')
    out.append("  )\n  (embedded_fonts no)\n)")
    return "\n".join(out)


CUSTOM_SYMBOLS = {
    "LIS2DH12": make_symbol(
        "LIS2DH12", "U", "LIS2DH12", "Package_LGA:LGA-12_2x2mm_P0.5mm",
        [("1", "SCL/SPC", "input", "L", 0, False), ("4", "SDA/SDI", "bidirectional", "L", 1, False),
         ("3", "SDO/SA0", "input", "L", 2, False), ("2", "CS", "input", "L", 3, False),
         ("12", "INT1", "output", "R", 0, False), ("11", "INT2", "output", "R", 1, False),
         ("9", "Vdd", "power_in", "T", 0, False), ("10", "Vdd_IO", "power_in", "T", 1, False),
         ("6", "GND", "power_in", "B", 0, False), ("7", "GND", "passive", "B", 0, True),
         ("8", "GND", "passive", "B", 0, True), ("5", "Res", "passive", "B", 1, False)],
        7.62, 7.62, "ST LIS2DH12 3-axis accelerometer, LGA-12 2x2 mm (pinout: datasheet DocID025056 Table 2)"),
    "SW_B3U": make_symbol(
        "SW_B3U", "SW", "B3U-3100P", "Button_Switch_SMD:SW_SPST_B3U-3100P",
        [("1", "1", "passive", "L", 0, False), ("2", "2", "passive", "R", 0, False),
         ("3", "GND", "passive", "B", 0, False)],
        2.54, 2.54, "Omron B3U-3100P side-actuated tactile switch, pin 3 = ground terminal"),
}


def write_project_libs():
    with open(os.path.join(PROJ, f"{NAME}.kicad_sym"), "w") as f:
        f.write('(kicad_symbol_lib (version 20241209) (generator "led_watch_generate") (generator_version "9.0")\n')
        for s in CUSTOM_SYMBOLS.values():
            f.write(s + "\n")
        f.write(")\n")
    os.makedirs(os.path.join(PROJ, f"{NAME}.pretty"), exist_ok=True)
    with open(os.path.join(PROJ, f"{NAME}.pretty", "BatteryHolder_MYOUNG_MY-2032-16.kicad_mod"), "w") as f:
        f.write(battery_footprint())
    # 0402 LED with an IPC least-density courtyard (0.1 mm round the pads): the library one is
    # 1.86 mm wide, the minute ring pitch is 1.81 mm.
    t = open(f"{KF}/LED_SMD.pretty/LED_0402_1005Metric.kicad_mod").read()
    t = t.replace('(footprint "LED_0402_1005Metric"', '(footprint "LED_0402_1005Metric_Tight"', 1)
    t = t.replace("(start -0.93 ", "(start -0.88 ").replace("(end -0.93 ", "(end -0.88 ")
    t = t.replace("(start 0.93 ", "(start 0.88 ").replace("(end 0.93 ", "(end 0.88 ")
    with open(os.path.join(PROJ, f"{NAME}.pretty", "LED_0402_1005Metric_Tight.kicad_mod"), "w") as f:
        f.write(t)
    for tbl, kind, path in [("sym-lib-table", "sym_lib_table", f"{NAME}.kicad_sym"),
                            ("fp-lib-table", "fp_lib_table", f"{NAME}.pretty")]:
        with open(os.path.join(PROJ, tbl), "w") as f:
            f.write(f'({kind}\n  (version 7)\n  (lib (name "{NAME}")(type "KiCad")'
                    f'(uri "${{KIPRJMOD}}/{path}")(options "")(descr "LED watch project library"))\n)\n')


def battery_footprint():
    """MYOUNG MY-2032-16 CR2032 clip (drawing MY-CP-0209): two + tabs 25.9 mm
    outside-to-outside (3.0 x 3.5 and 3.0 x 5.0 mm). The - contact is a copper
    pad on the PCB under the cell; four paste dots leave solder domes for contact pressure
    (007 board review #3), clear of the GND vias in its centre."""
    g = lambda *a: " ".join(f"{v:g}" for v in a)  # noqa: E731
    return f"""(footprint "BatteryHolder_MYOUNG_MY-2032-16"
  (version 20241229) (generator "led_watch_generate") (generator_version "9.0")
  (layer "F.Cu")
  (descr "MYOUNG MY-2032-16 SMT CR2032 clip, LCSC C2902340. Minus contact = PCB pad 2.")
  (tags "CR2032 coin cell battery holder")
  (property "Reference" "BT**" (at 0 -6.5 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
  (property "Value" "MY-2032-16" (at 0 6.5 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))
  (attr smd)
  (fp_circle (center 0 0) (end 10 0) (stroke (width 0.1) (type default)) (fill no) (layer "F.Fab"))
  (fp_rect (start -12.45 -4.5) (end 12.45 4.5) (stroke (width 0.1) (type default)) (fill no) (layer "F.Fab"))
  (fp_circle (center 0 0) (end 13.3 0) (stroke (width 0.05) (type default)) (fill no) (layer "F.CrtYd"))
  (fp_text user "+" (at {g(-9.2, -3.2)} 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
  (pad "1" smd rect (at {g(-11.45, 0)}) (size {g(3.0, 3.5)}) (layers "F.Cu" "F.Paste" "F.Mask"))
  (pad "1" smd rect (at {g(11.45, 0)}) (size {g(3.0, 5.0)}) (layers "F.Cu" "F.Paste" "F.Mask"))
  (pad "2" smd circle (at 0 0) (size 5.5 5.5) (layers "F.Cu" "F.Mask"))
  (pad "" smd circle (at 1.9 0) (size 1 1) (layers "F.Paste"))
  (pad "" smd circle (at -1.9 0) (size 1 1) (layers "F.Paste"))
  (pad "" smd circle (at 0 1.9) (size 1 1) (layers "F.Paste"))
  (pad "" smd circle (at 0 -1.9) (size 1 1) (layers "F.Paste"))
  (embedded_fonts no)
)
"""


# ============================================================ schematic
def pin_table(sym_text, names=False):
    """number -> (x, y, angle) [or -> pin name] from a symbol block."""
    import re
    res = {}
    for m in re.finditer(r'\(pin \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+) (\d+)\)[\s\S]*?\(name "([^"]*)"'
                         r'[\s\S]*?\(number "([^"]*)"', sym_text):
        res.setdefault(m.group(5), m.group(4) if names else (float(m.group(1)), float(m.group(2)), int(m.group(3))))
    return res


def write_schematic(parts, assign):
    mins, hours, anodes, blocks = assign
    root = U("root")
    libs = {}
    for p in parts:
        lib, name = p["lib_id"].split(":")
        if p["lib_id"] not in libs:
            if lib == NAME:
                s = CUSTOM_SYMBOLS[name].replace(f'(symbol "{name}"', f'(symbol "{NAME}:{name}"', 1)
            else:
                s = lib_symbol(lib, name)
            libs[p["lib_id"]] = s
    libs["power:PWR_FLAG"] = lib_symbol("power", "PWR_FLAG")
    pins = {k: pin_table(v) for k, v in libs.items()}
    pin_names = {k: pin_table(v, names=True) for k, v in libs.items()}
    for p in parts:   # KiCad names an unconnected pin's net "unconnected-(REF-PIN-PadN)"
        for n, nm in pin_names[p["lib_id"]].items():
            if p["pins"].get(n) is None:
                p.setdefault("nc_nets", {})[n] = f"unconnected-({p['ref']}-{nm}-Pad{n})"

    F = '(effects (font (size 1.27 1.27)))'
    FH = '(effects (font (size 1.27 1.27)) (hide yes))'
    items = []

    def label(net, x, y, a):
        rot, just = {0: (180, "right"), 180: (0, "left"), 90: (270, "right"), 270: (90, "left")}[a]
        items.append(f'(label "{net}" (at {x:.2f} {y:.2f} {rot}) (fields_autoplaced yes)'
                     f' (effects (font (size 1.27 1.27)) (justify {just} bottom)) (uuid "{U("lbl", net, x, y)}"))')

    def place(p, x, y):
        tbl = pins[p["lib_id"]]
        ref = p["ref"]
        props = [("Reference", ref, F, 0, -6.35), ("Value", p["value"], F, 0, 6.35),
                 ("Footprint", p["fp"], FH, 0, 0), ("Datasheet", "~", FH, 0, 0),
                 ("Description", "", FH, 0, 0), ("LCSC", p.get("lcsc", ""), FH, 0, 0)]
        in_bom = "no" if p["kind"] == "TP" else "yes"
        pr = "\n".join(f'  (property "{k}" "{v}" (at {x + dx:.2f} {y + dy:.2f} 0) {e})' for k, v, e, dx, dy in props)
        pin_uuids = " ".join(f'(pin "{n}" (uuid "{U("pin", ref, n)}"))' for n in tbl)
        items.append(f'(symbol (lib_id "{p["lib_id"]}") (at {x:.2f} {y:.2f} 0) (unit 1) (exclude_from_sim no)'
                     f' (in_bom {in_bom}) (on_board yes) (dnp {"yes" if p.get("dnp") else "no"}) (uuid "{U("sym", ref)}")\n{pr}\n  {pin_uuids}\n'
                     f'  (instances (project "{NAME}" (path "/{root}" (reference "{ref}") (unit 1)))))')
        done = set()
        for n, (px, py, a) in tbl.items():
            ex, ey = round(x + px, 2), round(y - py, 2)
            if (ex, ey) in done:
                continue
            done.add((ex, ey))
            net = p["pins"].get(n)
            if net:
                label(net, ex, ey, a)
            else:
                items.append(f'(no_connect (at {ex:.2f} {ey:.2f}) (uuid "{U("nc", ref, n)}"))')

    def flag(i, net, x, y):
        items.append(f'(symbol (lib_id "power:PWR_FLAG") (at {x:.2f} {y:.2f} 0) (unit 1) (exclude_from_sim no)'
                     f' (in_bom no) (on_board no) (dnp no) (uuid "{U("flg", i)}")\n'
                     f'  (property "Reference" "#FLG0{i}" (at {x:.2f} {y - 3.81:.2f} 0) {FH})\n'
                     f'  (property "Value" "PWR_FLAG" (at {x:.2f} {y - 5.08:.2f} 0) {F})\n'
                     f'  (property "Footprint" "" (at {x:.2f} {y:.2f} 0) {FH})\n'
                     f'  (property "Datasheet" "~" (at {x:.2f} {y:.2f} 0) {FH})\n'
                     f'  (pin "1" (uuid "{U("flgpin", i)}"))\n'
                     f'  (instances (project "{NAME}" (path "/{root}" (reference "#FLG0{i}") (unit 1)))))')
        label(net, x, y, 90)

    def text(s, x, y, size=1.27):
        s = s.replace('"', "'")
        items.append(f'(text "{s}" (exclude_from_sim no) (at {x:.2f} {y:.2f} 0)'
                     f' (effects (font (size {size} {size})) (justify left bottom)) (uuid "{U("txt", x, y)}"))')

    byref = {p["ref"]: p for p in parts}
    g = 2.54
    # --- MCU, accelerometer, crystal
    place(byref["U1"], 30 * g, 40 * g)
    place(byref["U2"], 62 * g, 26 * g)
    place(byref["R10"], 52 * g, 18 * g)
    place(byref["R11"], 56 * g, 18 * g)
    place(byref["C4"], 72 * g, 22 * g)
    place(byref["Y1"], 56 * g, 48 * g)
    place(byref["C5"], 52 * g, 54 * g)
    place(byref["C6"], 60 * g, 54 * g)
    # --- power
    place(byref["BT1"], 10 * g, 76 * g)
    place(byref["Q1"], 20 * g, 72 * g)
    for i, r in enumerate(["C1", "C3"]):
        place(byref[r], (30 + 6 * i) * g, 74 * g)
    flag(1, "VBAT", 14 * g, 66 * g)
    flag(2, "VDD", 26 * g, 66 * g)
    flag(3, "GND", 18 * g, 84 * g)
    # --- buttons + programming pads
    place(byref["SW1"], 52 * g, 70 * g)
    place(byref["SW2"], 52 * g, 80 * g)
    place(byref["C7"], 62 * g, 70 * g)
    place(byref["C8"], 62 * g, 80 * g)
    place(byref["R12"], 44 * g, 70 * g)
    place(byref["R13"], 44 * g, 80 * g)
    place(byref["D73"], 68 * g, 70 * g)
    place(byref["D74"], 68 * g, 80 * g)
    for i in range(4):
        place(byref[f"TP{i+1}"], (8 + 6 * i) * g, 100 * g)
    # --- LED line resistors and the 72 LEDs
    for k in range(D.N_LINES):
        place(byref[f"R{k+1}"], (80 + 6 * k) * g, 100 * g)
    for i in range(72):
        ref = f"D{i+1}"
        col, row = i % 12, i // 12
        place(byref[ref], (80 + 7 * col) * g, (14 + 5 * row) * g)
    text("LED WATCH - charlieplexed display", 80 * g, 6 * g, 2.0)
    text("D1-D60: minute LEDs, Dn = minute n-1 (D1 at 12 o'clock, clockwise). D61-D72: hour LEDs, D61 = 12 o'clock.",
         80 * g, 8 * g)
    text("Each LED: K -> cathode line, A -> anode line. Lines L0-L8 drive through R1-R9 from the MCU (Lk_M).",
         80 * g, 10 * g)
    text("Lit LED: anode line high, cathode line low, other 7 lines Hi-Z. One LED on at a time.", 80 * g, 12 * g)
    pinmap = ", ".join(f"L{k}={D.MCU_PORTPIN[n]}" for k in range(9) for n, net in D.MCU_PINS.items() if net == f"L{k}_M")
    text("MCU lines: " + pinmap, 8 * g, 10 * g)
    text("Buttons: SW_A=PC2 (show time, async pin), SW_B=PC3. ACC_INT=PC0. I2C: SDA=PB1 SCL=PB0 (LIS2DH12 addr 0x19).", 8 * g, 12 * g)
    text("UPDI=PA0, TX=PA1 (USART0 alt). XTAL on TOSC1/TOSC2 (PB3/PB2). BT1 -> Q1 reverse-polarity P-FET -> VDD.", 8 * g, 14 * g)
    text("No VDD pad on purpose: program from the cell (UPDI + GND). Never feed VDD with a cell fitted: Q1 conducts both ways.", 8 * g, 16 * g)
    text("RTC = PA2 (EVOUT0) test pad for crystal calibration. D73/D74 ESD footprints not fitted.", 8 * g, 18 * g)

    body = "\n".join(items)
    sch = (f'(kicad_sch (version 20250114) (generator "eeschema") (generator_version "9.0") (uuid "{root}") (paper "A3")\n'
           f'(title_block (title "LED analogue watch") (rev "A") (company "agent 003") (comment 1 "Generated by tools/generate.py"))\n'
           f'(lib_symbols\n' + "\n".join(libs.values()) + "\n)\n" + body +
           '\n(sheet_instances (path "/" (page "1")))\n(embedded_fonts no)\n)\n')
    with open(os.path.join(PROJ, f"{NAME}.kicad_sch"), "w") as f:
        f.write(sch)
    return root


def write_pinmap(assign):
    """PINMAP.md: the firmware's view of the board, generated so it cannot drift."""
    mins, hours, anodes, blocks = assign
    pin_of = {net: n for n, net in D.MCU_PINS.items() if net}
    L = ["# LED watch pin map (generated by tools/generate.py - do not edit)", "",
         "MCU: ATtiny3217, VQFN-24. Board rev A.", "",
         "| Signal | MCU pin | Port | Notes |", "|---|---|---|---|"]
    notes = {"SW_A": "button A (2 o'clock), to GND via 1k, 100 nF at MCU; fully async pin",
             "SW_B": "button B (4 o'clock), to GND via 1k, 100 nF at MCU; NOT async: wake with BOTHEDGES/LEVEL",
             "ACC_INT": "LIS2DH12 INT1, push-pull from the sensor; NOT async: BOTHEDGES/LEVEL",
             "SDA": "TWI0, 4.7k pull-up (fitted with U2)", "SCL": "TWI0, 4.7k pull-up (fitted with U2)",
             "XT1": "TOSC1, 32.768 kHz 7 pF crystal", "XT2": "TOSC2",
             "UPDI": "pogo pad TP1", "TX": "USART0 TxD (alternate pin), pad TP3",
             "RTC": "EVOUT0 test pad TP4 (route RTC/PIT event here to measure the crystal)"}
    for net in ["SW_A", "SW_B", "ACC_INT", "SDA", "SCL", "XT1", "XT2", "UPDI", "TX", "RTC"]:
        n = pin_of[net]
        L.append(f"| {net} | {n} | {D.MCU_PORTPIN[n]} | {notes[net]} |")
    for k in range(D.N_LINES):
        n = pin_of[f"L{k}_M"]
        L.append(f"| L{k} | {n} | {D.MCU_PORTPIN[n]} | charlieplex line, 100 R series |")
    spare = [f"{D.MCU_PORTPIN[n]} (pin {n})" for n, net in D.MCU_PINS.items() if net is None]
    L += ["", "Spare, not connected: " + ", ".join(spare) + ".",
          "LIS2DH12: I2C address 0x19 (SA0 tied high), CS high, on the TOP side (+Z out of the dial).",
          "", "## LEDs", "",
          "Index = firmware numbering: 0-59 minutes clockwise from 12, 60-71 hours from 12.",
          "Light LED i: line A high, line K low, all other lines input with INPUT_DISABLE.", "",
          "| LED | Ref | Anode line | Cathode line |", "|---|---|---|---|"]
    for m in range(60):
        L.append(f"| {m} | D{m+1} | L{mins[m][0]} | L{mins[m][1]} |")
    for h in range(12):
        L.append(f"| {60+h} | D{61+h} | L{hours[h][0]} | L{hours[h][1]} |")
    L += ["", "## Firmware rules from the hardware review (007)", "",
          "- Never drive VDD from the programmer: there is no VDD pad; program from the cell (UPDI + GND).",
          "- BOD off in sleep (or sampled at 125 Hz): continuous BOD costs ~20 uA.",
          "- In sleep set INPUT_DISABLE (or drive low) on all 9 LED lines and on the spare pins.",
          "- When switching LEDs, set all line DIR bits to input first, then set the new pair.",
          "- Refuse to light LEDs below ~2.4 V (measure VDD against the internal reference)."]
    with open(os.path.join(PROJ, "PINMAP.md"), "w") as f:
        f.write("\n".join(L) + "\n")


def main():
    parts, assign = build_parts()
    write_project_libs()
    root = write_schematic(parts, assign)
    write_pinmap(assign)
    print("schematic written")
    if "--sch-only" in sys.argv:
        return
    for p in parts:
        p["sym_uuid"] = U("sym", p["ref"])
    import board
    order = list(board.DEFAULT_ORDER)
    pcb = os.path.join(PROJ, f"{NAME}.kicad_pcb")
    best = None
    for attempt in range(6):
        failures, links, spokes = board.build_board(parts, assign, root, pcb, order)
        print(f"attempt {attempt + 1}: unrouted {failures}")
        if best is None or len(failures) < len(best[0]):
            best = (failures, list(order))
            os.replace(pcb, pcb + ".best")
        if not failures:
            break
        bad = []
        for n, _, _ in failures:
            if n not in bad and n != "GND":   # GND is dropped to the planes, not routed as a tree
                bad.append(n)
        bad = [n for n in bad if n not in ("VDD", "VBAT")]
        # rip up: failures first, then power (F.Cu only under the cell), then the rest
        order = bad + ["VDD", "VBAT"] + [n for n in order if n not in bad and n not in ("VDD", "VBAT")]
    failures = best[0]
    os.replace(pcb + ".best", pcb)
    # footprint silkscreen was moved to Fab on purpose (dense board), so the
    # "footprint differs from library" warning is expected: switch it off here.
    import json
    pro = os.path.join(PROJ, f"{NAME}.kicad_pro")
    with open(pro) as f:
        cfg = json.load(f)
    cfg.setdefault("board", {}).setdefault("design_settings", {}).setdefault("rule_severities", {})[
        "lib_footprint_mismatch"] = "ignore"
    with open(pro, "w") as f:
        json.dump(cfg, f, indent=2)
    print("pcb written; spokes (line -> boundary):", spokes)
    if failures:
        print("UNROUTED:", failures)
        sys.exit(2)

if __name__ == "__main__":
    main()
