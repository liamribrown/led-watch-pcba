#!/usr/bin/env python3
"""Regression test for check_cell.py: the real board must pass, and copies with copper sneaked
under the CR2032 must fail, including cases where every end point / vertex is OUTSIDE the
keep-out (the gap found in review).

    python3 tools/test_check_cell.py          # from projects/led-watch
"""
import os
import subprocess
import sys
import tempfile

import pcbnew as pn

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(os.path.dirname(HERE), "led-watch.kicad_pcb")
CHECK = os.path.join(HERE, "check_cell.py")
mm = pn.FromMM


def V(x, y):
    return pn.VECTOR2I(mm(100 + x), mm(100 + y))


def rect(x0, y0, x1, y1):
    ps = pn.SHAPE_POLY_SET()
    ps.NewOutline()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        ps.Append(mm(100 + x), mm(100 + y))
    return ps


def add_fill(b, ps):
    z = pn.ZONE(b)
    z.SetLayer(pn.B_Cu)
    z.SetNet(b.FindNet("/GND"))
    o = z.Outline()
    o.NewOutline()
    for i in range(ps.Outline(0).PointCount()):
        q = ps.Outline(0).CPoint(i)
        o.Append(q.x, q.y)
    b.Add(z)
    z.SetFilledPolysList(pn.B_Cu, ps)
    z.SetIsFilled(True)


def add_track(b):
    t = pn.PCB_TRACK(b)
    t.SetStart(V(-15, 0.3))
    t.SetEnd(V(15, 0.3))
    t.SetWidth(mm(0.2))
    t.SetLayer(pn.B_Cu)
    t.SetNet(b.FindNet("/GND"))
    b.Add(t)


def run(path):
    r = subprocess.run([sys.executable, CHECK, path], capture_output=True, text=True)
    return r.returncode, [l for l in r.stdout.splitlines() if l.startswith("FAIL")]


def main():
    ok = True
    code, fails = run(PCB)
    print(f"real board: {'pass' if code == 0 else 'FAIL ' + str(fails)}")
    ok &= code == 0
    cases = {
        "B.Cu track across the cell, both ends outside": add_track,
        "B.Cu pour strip across the cell, all vertices outside": lambda b: add_fill(b, rect(-15, 3.0, 15, 3.6)),
        "B.Cu pour over the whole cell, all corners outside": lambda b: add_fill(b, rect(-15, -15, 15, 15)),
    }
    with tempfile.TemporaryDirectory() as d:
        for i, (name, mutate) in enumerate(cases.items()):
            b = pn.LoadBoard(PCB)
            mutate(b)
            p = os.path.join(d, f"case{i}.kicad_pcb")
            pn.SaveBoard(p, b)
            code, fails = run(p)
            caught = code == 1 and fails
            print(f"{name}: {'caught: ' + fails[0] if caught else 'MISSED'}")
            ok &= bool(caught)
    print("test_check_cell:", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
