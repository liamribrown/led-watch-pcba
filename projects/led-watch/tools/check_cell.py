#!/usr/bin/env python3
"""Check the copper under the CR2032 (007 board review #1). Exit 1 on any violation.

    python3 tools/check_cell.py [led-watch.kicad_pcb]

Rules (cell centred on the board, radius 10 mm, keep-out r <= 10.5 mm):
  - B.Cu: no tracks (whole segments, arcs sampled), no zone fill (the fill must not contain the
    centre and no outline/hole edge may come inside the keep-out) and no pads except BT1's.
  - VBAT and VDD: no vias under the cell (their copper would short the cell through a
    scratched mask).
  - GND vias under the cell only below the minus cap (r < 6.7 mm).
  - Vias under the cell keep no copper ring on B.Cu (except GND vias inside the minus pad).
Other vias under the cell are current-limited signals (LED lines, I2C, buttons).
"""
import math
import sys
from collections import Counter

import pcbnew as pn

CX, CY = 100.0, 100.0
R_KEEP, R_GND = 10.5, 6.7
R_MINUS_PAD = 2.75          # BT1 pad 2 (cell minus contact), GND


def r_of(v):
    return math.hypot(pn.ToMM(v.x) - CX, pn.ToMM(v.y) - CY)


def seg_r(t):
    """Distance from the board centre to the closest point of a track segment (arcs: sampled)."""
    if t.Type() == pn.PCB_ARC_T:
        c, rad = t.GetCenter(), pn.ToMM(t.GetRadius())
        a0 = math.atan2(pn.ToMM(t.GetStart().y - c.y), pn.ToMM(t.GetStart().x - c.x))
        a1 = math.atan2(pn.ToMM(t.GetEnd().y - c.y), pn.ToMM(t.GetEnd().x - c.x))
        am = math.atan2(pn.ToMM(t.GetMid().y - c.y), pn.ToMM(t.GetMid().x - c.x))
        span = (a1 - a0) % (2 * math.pi)
        if (am - a0) % (2 * math.pi) > span:
            span -= 2 * math.pi
        return min(math.hypot(pn.ToMM(c.x) + rad * math.cos(a0 + span * k / 64) - CX,
                              pn.ToMM(c.y) + rad * math.sin(a0 + span * k / 64) - CY) for k in range(65))
    ax, ay = pn.ToMM(t.GetStart().x) - CX, pn.ToMM(t.GetStart().y) - CY
    bx, by = pn.ToMM(t.GetEnd().x) - CX, pn.ToMM(t.GetEnd().y) - CY
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    u = 0.0 if L2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / L2))
    return math.hypot(ax + u * dx, ay + u * dy)


def poly_edge_r(a, b):
    """Distance from the board centre to the closest point of the edge a-b."""
    ax, ay = pn.ToMM(a.x) - CX, pn.ToMM(a.y) - CY
    bx, by = pn.ToMM(b.x) - CX, pn.ToMM(b.y) - CY
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    u = 0.0 if L2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / L2))
    return math.hypot(ax + u * dx, ay + u * dy)


def main(path):
    b = pn.LoadBoard(path)
    bad = []
    for t in b.GetTracks():
        if t.Type() == pn.PCB_VIA_T:
            r = r_of(t.GetPosition())
            net = t.GetNetname().lstrip("/")
            if r - 0.25 <= R_KEEP:
                if net in ("VBAT", "VDD"):
                    bad.append(f"{net} via under the cell at r = {r:.2f} mm")
                if net == "GND" and r + 0.25 > R_GND:
                    bad.append(f"GND via under the cell outside the minus cap at r = {r:.2f} mm")
                if t.FlashLayer(pn.B_Cu) and r > R_MINUS_PAD - 0.25:   # inside pad 2 the ring is the pad
                    bad.append(f"{net} via at r = {r:.2f} mm keeps a B.Cu ring")
        elif t.GetLayer() == pn.B_Cu:
            r = seg_r(t)   # closest point of the whole segment, not just its ends (007 note N3)
            if r - pn.ToMM(t.GetWidth()) / 2 <= R_KEEP:
                bad.append(f"B.Cu track {t.GetNetname()} under the cell (r = {r:.2f} mm)")
    centre = pn.VECTOR2I(pn.FromMM(CX), pn.FromMM(CY))
    for z in b.Zones():
        if z.GetIsRuleArea() or not z.IsOnLayer(pn.B_Cu):
            continue
        fill = z.GetFilledPolysList(pn.B_Cu)
        name = f"B.Cu zone {z.GetNetname()} fill"
        # a pour can cross under the cell with every vertex outside it, so test the area and edges
        if fill.OutlineCount() and fill.Contains(centre):
            bad.append(f"{name} covers the board centre")
        for k in range(fill.OutlineCount()):
            chains = [fill.COutline(k)] + [fill.CHole(k, h) for h in range(fill.HoleCount(k))]
            for ch in chains:
                n = ch.PointCount()
                r = min((poly_edge_r(ch.CPoint(i), ch.CPoint((i + 1) % n)) for i in range(n)), default=99)
                if r < R_KEEP - 0.02:
                    bad.append(f"{name} edge reaches r = {r:.2f} mm (keep-out {R_KEEP} mm)")
    # B.Cu pads under the cell: only BT1 (minus pad and + tabs)
    for fp in b.GetFootprints():
        if fp.GetReference() == "BT1":
            continue
        for p in fp.Pads():
            if p.IsOnLayer(pn.B_Cu) and r_of(p.GetPosition()) - pn.ToMM(max(p.GetSize(pn.B_Cu).x, p.GetSize(pn.B_Cu).y)) / 2 <= R_KEEP:
                bad.append(f"B.Cu pad {fp.GetReference()}.{p.GetNumber()} under the cell")
    vias = Counter(t.GetNetname().lstrip("/") for t in b.GetTracks()
                   if t.Type() == pn.PCB_VIA_T and r_of(t.GetPosition()) - 0.25 <= R_KEEP)
    print("vias under the cell by net:", dict(sorted(vias.items())))
    for m in bad:
        print("FAIL:", m)
    print("cell check:", "FAIL" if bad else "OK")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "led-watch.kicad_pcb"))
