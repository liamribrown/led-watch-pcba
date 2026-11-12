#!/usr/bin/env python3
"""Export the board geometry as JSON for the 3D browser simulator (projects/watch-sim).

    python3 tools/export_3d.py [led-watch.kicad_pcb] [board-geometry.json]

Units mm, origin at the board centre, +x right, +y toward 12 o'clock seen from the top.
rotation_deg is counter-clockwise seen from the top. The file holds geometry and refs only.
EXACT (read from the board): outline radius, thickness, every x, y, rotation, side, pad
position/diameter, footprint bounding box (w, h in the part's own unrotated frame).
SIMPLIFIED: part heights (typical package values), body shapes (a box = the footprint bounding
box, which includes pads), the CR2032 (20 x 3.2 mm cylinder) and its holder outline.
"""
import json
import os
import sys

import pcbnew as pn

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PCB = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "led-watch.kicad_pcb")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "board-geometry.json")
mm = pn.ToMM
CX, CY = 100.0, 100.0

HEIGHTS = {"U1": 0.9, "U2": 1.0, "Y1": 0.8, "Q1": 1.1, "SW1": 4.0, "SW2": 4.0, "BT1": 5.0}


def xy(p):
    return round(mm(p.x) - CX, 3), round(-(mm(p.y) - CY), 3)


def local_box(fp):
    """w, h and centre offset of the footprint bounding box in its own frame (no text)."""
    c = pn.FOOTPRINT(fp)
    c.SetOrientationDegrees(0)
    if fp.GetLayer() == pn.B_Cu:
        c.Flip(c.GetPosition(), False)
    bb = c.GetBoundingBox(False)
    p = c.GetPosition()
    return (round(mm(bb.GetWidth()), 3), round(mm(bb.GetHeight()), 3),
            round(mm(bb.GetCenter().x - p.x), 3), round(-mm(bb.GetCenter().y - p.y), 3))


def part(fp, kind, height):
    x, y = xy(fp.GetPosition())
    w, h, ox, oy = local_box(fp)
    return {"ref": fp.GetReference(), "kind": kind, "x": x, "y": y,
            "rotation_deg": round(-fp.GetOrientationDegrees() % 360, 3),
            "w": w, "h": h, "offset_x": ox, "offset_y": oy, "height": height,
            "side": "bottom" if fp.GetLayer() == pn.B_Cu else "top"}


def main():
    b = pn.LoadBoard(PCB)
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    radius = None
    for d in b.GetDrawings():
        if d.GetLayer() == pn.Edge_Cuts and d.GetShape() == pn.SHAPE_T_CIRCLE:
            radius = round(mm(d.GetRadius()), 3)
    leds = []
    for n in range(1, 73):                       # D1..D60 minutes (index 0..59), D61..D72 hours (60..71)
        fp = fps[f"D{n}"]
        p = part(fp, "led", 0.4 if n <= 60 else 0.5)
        leds.append({"index": n - 1, "ref": p["ref"], "x": p["x"], "y": p["y"],
                     "rotation_deg": p["rotation_deg"],
                     "package": "0402" if n <= 60 else "0603",
                     "colour": "amber" if n <= 60 else "red", "side": p["side"],
                     "w": p["w"], "h": p["h"]})
    parts = [part(fps[r], k, HEIGHTS[r]) for r, k in
             (("U1", "mcu_vqfn24"), ("U2", "accelerometer_lga12"), ("Y1", "crystal"), ("Q1", "fet_sot23"))]
    for ref, fp in sorted(fps.items()):
        if ref[0] in "RC" and ref[1:].isdigit():
            parts.append(part(fp, "resistor" if ref[0] == "R" else "capacitor", 0.4))
    bt = fps["BT1"]
    bw, bh, _, _ = local_box(bt)
    buttons = []
    for name, ref in (("A", "SW1"), ("B", "SW2")):
        p = part(fps[ref], "button", HEIGHTS[ref])
        p["name"] = name
        buttons.append(p)
    pads = []
    for t in ("TP1", "TP2", "TP3", "TP4"):
        for pad in fps[t].Pads():
            x, y = xy(pad.GetPosition())
            pads.append({"ref": t, "net": pad.GetNetname().lstrip("/"), "x": x, "y": y,
                         "diameter": round(mm(pad.GetSize().x), 3), "side": "bottom" if fps[t].GetLayer() == pn.B_Cu else "top"})
    data = {
        "units": "mm", "generator": "led-watch/tools/export_3d.py",
        "frame": "origin at board centre, +x right, +y toward 12 o'clock seen from the top, rotation counter-clockwise from the top",
        "board": {"diameter": round(2 * radius, 3), "edge_cut_radius": radius,
                  "thickness": round(mm(b.GetDesignSettings().GetBoardThickness()), 3),
                  "copper_layers": b.GetCopperLayerCount()},
        "leds": leds, "parts": parts,
        "battery": {"ref": "BT1", "side": "bottom", "x": xy(bt.GetPosition())[0], "y": xy(bt.GetPosition())[1],
                    "holder_w": bw, "holder_h": bh, "holder_height": HEIGHTS["BT1"],
                    "cell_diameter": 20.0, "cell_height": 3.2},
        "buttons": buttons, "pads": pads,
        "exact": ["board.*", "leds[].x/y/rotation_deg/side", "parts[].x/y/rotation_deg/w/h/side", "buttons[].x/y/w/h/side", "pads[]"],
        "simplified": ["heights", "part bodies as boxes", "battery.holder_* (footprint bounding box)", "cell cylinder"],
    }
    os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(data, f, indent=1)
    print(f"3d: {len(leds)} leds, {len(parts)} parts, {len(buttons)} buttons, {len(pads)} pads -> {os.path.basename(OUT)}")


if __name__ == "__main__":
    main()
