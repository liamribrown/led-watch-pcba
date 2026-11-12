"""LED watch: design data shared by the schematic and PCB generators.

Everything electrical lives here: parts, LCSC numbers, pin-to-net maps, and the
charlieplex LED assignment. generate.py turns it into KiCad files.
"""
import math
import random

# ---------------------------------------------------------------- parts / LCSC
# LCSC numbers and stock were checked on lcsc.com on 2026-11-11 (see SPEC.md / BOM).
P = {
    "MCU":   dict(value="ATtiny3217-MNR", lcsc="C614177", fp="Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm"),
    "ACC":   dict(value="LIS2DH12TR", lcsc="C110926", fp="Package_LGA:LGA-12_2x2mm_P0.5mm"),
    "XTAL":  dict(value="32.768kHz 7pF", lcsc="C5136974", fp="Crystal:Crystal_SMD_2012-2Pin_2.0x1.2mm"),
    "FET":   dict(value="AO3401A", lcsc="C15127", fp="Package_TO_SOT_SMD:SOT-23"),
    "BAT":   dict(value="MY-2032-16 (CR2032)", lcsc="C2902340", fp="led-watch:BatteryHolder_MYOUNG_MY-2032-16"),
    "SW":    dict(value="B3U-3100P", lcsc="C6748648", fp="Button_Switch_SMD:SW_SPST_B3U-3100P"),
    "LED_M": dict(value="Yellow 590nm XL-1005UYC", lcsc="C25503856", fp="led-watch:LED_0402_1005Metric_Tight"),
    "LED_H": dict(value="Red 639nm LTST-C191KRKT", lcsc="C125099", fp="LED_SMD:LED_0603_1608Metric"),
    "R100":  dict(value="100", lcsc="C25076", fp="Resistor_SMD:R_0402_1005Metric"),
    "R4k7":  dict(value="4.7k", lcsc="C25900", fp="Resistor_SMD:R_0402_1005Metric"),
    "C100n": dict(value="100nF", lcsc="C1525", fp="Capacitor_SMD:C_0402_1005Metric"),
    "C6p8":  dict(value="6.8pF C0G", lcsc="C1576", fp="Capacitor_SMD:C_0402_1005Metric"),
    "C10u":  dict(value="10uF", lcsc="C19702", fp="Capacitor_SMD:C_0603_1608Metric"),
    "C22u":  dict(value="22uF", lcsc="C45783", fp="Capacitor_SMD:C_0805_2012Metric"),
    "TP":    dict(value="TP", lcsc="", fp="TestPoint:TestPoint_Pad_D1.0mm"),
    "R1k":   dict(value="1k", lcsc="C11702", fp="Resistor_SMD:R_0402_1005Metric"),
    "TVS":   dict(value="ESD TVS 5V bidir (DNP)", lcsc="", fp="Diode_SMD:D_0402_1005Metric"),
}

N_LINES = 9                      # charlieplex lines L0..L8 -> 9*8 = 72 LEDs

# ATtiny3217 VQFN-24 pin -> net. Pin numbers/functions from the datasheet I/O
# multiplexing table (TOSC1=PB3, TOSC2=PB2, SDA=PB1, SCL=PB0, UPDI=PA0, TxD alt=PA1).
MCU_PINS = {
    "1": "RTC",    # PA2 = EVOUT0: RTC/PIT event out to a test pad for crystal calibration
    "2": "L0_M",   # PA3
    "3": "GND",
    "4": "VDD",
    "5": "L1_M",   # PA4
    "6": "L2_M",   # PA5
    "7": "L3_M",   # PA6
    "8": "L4_M",   # PA7
    "9": "L5_M",   # PB7
    "10": "L6_M",  # PB6
    "11": "L7_M",  # PB5
    "12": "L8_M",  # PB4
    "13": "XT1",   # PB3 TOSC1
    "14": "XT2",   # PB2 TOSC2
    "15": "SDA",   # PB1
    "16": "SCL",   # PB0
    "17": "ACC_INT",  # PC0
    "18": None,    # PC1 spare
    "19": "SW_A",  # PC2 (fully async pin: any edge wakes from any sleep)
    "20": "SW_B",  # PC3 (use BOTHEDGES/LEVEL sense to wake from standby)
    "21": None, "22": None,   # PC4, PC5 spare
    "23": "UPDI",  # PA0
    "24": "TX",    # PA1 (USART0 TxD, alternate position)
    "25": "GND",   # exposed pad
}
MCU_PORTPIN = {"1": "PA2", "2": "PA3", "5": "PA4", "6": "PA5", "7": "PA6", "8": "PA7",
               "9": "PB7", "10": "PB6", "11": "PB5", "12": "PB4", "19": "PC2", "20": "PC3", "17": "PC0",
               "15": "PB1", "16": "PB0", "13": "PB3", "14": "PB2", "23": "PA0", "24": "PA1",
               "18": "PC1", "21": "PC4", "22": "PC5"}

# LIS2DH12 (datasheet Table 2). SDO/SA0 has an internal pull-up: tie it HIGH,
# tying it low would waste ~100 uA. CS high selects I2C. Address = 0x19.
ACC_PINS = {"1": "SCL", "2": "VDD", "3": "VDD", "4": "SDA", "5": "GND", "6": "GND",
            "7": "GND", "8": "GND", "9": "VDD", "10": "VDD", "11": None, "12": "ACC_INT"}

# ---------------------------------------------------------------- LED geometry
# Clock positions: minute m at 6*m degrees, hour h at 30*h degrees (clockwise from 12).
TAB_MINUTES = set(range(13, 18)) | set(range(43, 48))   # coin-cell tabs under these
BUTTON_MINUTES = {10, 20}                                # B3U ground pad under these
MIN_BLOCK_START = 6


def ring_ok(m, c):
    """Can a cathode via on ring c sit in minute sector m? (see generate.py geometry)"""
    if m in TAB_MINUTES and c < 5:
        return False          # via would hit the battery-holder tab on B.Cu
    if m in BUTTON_MINUTES and c > 6:
        return False          # via would hit the switch ground pad on B.Cu
    return True


def assign_leds(seed=7):
    """Return (minute_leds, hour_leds) as dicts index -> (anode_line, cathode_line).

    Blocks of 8 LEDs share an anode line, so their anodes join with one copper arc
    and every LED needs only one via (for its cathode). Blocks 0..6 are minutes
    6..61 (mod 60), block 7 is minutes 2..5 + hours 0..3, block 8 is hours 4..11.
    """
    rnd = random.Random(seed)
    blocks = [[("m", (MIN_BLOCK_START + 8 * b + i) % 60) for i in range(8)] for b in range(7)]
    blocks.append([("m", m) for m in (2, 3, 4, 5)] + [("h", h) for h in (0, 1, 2, 3)])
    blocks.append([("h", h) for h in range(4, 12)])
    for _ in range(20000):
        anodes = list(range(N_LINES))
        rnd.shuffle(anodes)
        res_m, res_h, ok = {}, {}, True
        # minutes first (hours must avoid the minute cathode in the same sector)
        order = sorted(range(9), key=lambda b: any(k == "h" for k, _ in blocks[b]))
        for b in order:
            a = anodes[b]
            cath = [c for c in range(N_LINES) if c != a]
            leds = blocks[b]

            def ok_for(kind, idx, c):
                if kind == "m":
                    return ring_ok(idx, c)
                m = 5 * idx
                return ring_ok(m, c) and res_m.get(m, (None, None))[1] != c

            # backtracking assignment of the 8 cathodes in this block
            sol = [None] * 8

            def bt(i, free):
                if i == 8:
                    return True
                kind, idx = leds[i]
                opts = [c for c in free if ok_for(kind, idx, c)]
                rnd.shuffle(opts)
                for c in opts:
                    sol[i] = c
                    if bt(i + 1, free - {c}):
                        return True
                return False

            if not bt(0, frozenset(cath)):
                ok = False
                break
            for (kind, idx), c in zip(leds, sol):
                (res_m if kind == "m" else res_h)[idx] = (a, c)
        if ok:
            return res_m, res_h, anodes, blocks
    raise RuntimeError("no LED assignment found")


if __name__ == "__main__":
    m, h, anodes, blocks = assign_leds()
    print("block anodes:", anodes)
    for i in range(60):
        print(f"minute {i:2d}: anode L{m[i][0]} cathode L{m[i][1]}")
    for i in range(12):
        print(f"hour   {i:2d}: anode L{h[i][0]} cathode L{h[i][1]}")
