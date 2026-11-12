"""LED watch PCB builder: placement, the regular LED/ring structure, and a small
grid router (A*) for the remaining connections in the centre of the board."""
import heapq
import math
import os

import numpy as np
import pcbnew as pn

import design as D
from generate import (CX, CY, R_BOARD, R_MIN_LED, R_ARC_OUT, R_HOUR_LED, R_ARC_IN, R_SPOKE_IN, R_RES,
                      HOUR_VIA_OFF, TRACK, TRACK_R, CLEAR, VIA_D, VIA_DRILL, KF, NAME, PROJ,
                      ring_r, polar, clock_deg)

mm = pn.FromMM
LAYERS = [pn.F_Cu, pn.In1_Cu, pn.In2_Cu, pn.B_Cu]
LF, LIN1, LIN2, LB = 0, 1, 2, 3


def V(x, y):
    return pn.VECTOR2I(mm(x), mm(y))


def tomm(v):
    return pn.ToMM(v.x), pn.ToMM(v.y)


# ============================================================ inner placement (offsets from centre, mm; y down)
INNER = {
    "U1": (0.0, 0.0, 0),
    "C1": (-3.6, 0.0, 180),     # VDD pad next to MCU pin 4
    "C3": (2.4, -5.8, 0),       # 22 uF bulk next to Q1
    "U2": (4.9, -0.3, 180),     # I2C/CS/SA0 face outwards (to the pull-ups), VDD/GND face the MCU
    "C4": (6.4, -3.1, 90),
    "R10": (7.2, 1.0, 90),      # SCL pull-up, beside U2 pin 1
    "R11": (7.2, -1.2, 90),     # SDA pull-up, beside U2 pin 4
    "Y1": (4.2, 3.3, 90),       # vertical: XT2 (upper MCU pin) to the top pad, XT1 to the bottom
    "C5": (6.3, 4.2, 0),        # XT1 load cap beside Y1 pad 1 (bottom)
    "C6": (6.3, 2.4, 0),        # XT2 load cap beside Y1 pad 2 (top)
    "C7": (1.9, -3.75, 90),
    "C8": (0.6, -3.75, 90),
}
BUTTONS = {"SW1": 60.0, "SW2": 120.0}            # 2 and 4 o'clock, bottom side
R_BUTTON = 16.45                                  # plunger outline ends at r 19.38, ~0.4 mm past the edge
TESTPADS = {"TP1": -3.81, "TP2": -1.27, "TP3": 1.27, "TP4": 3.81}   # UPDI GND TX RTC, 12 o'clock
BUTTON_PARTS = {"R12": ("SW1", -13), "D73": ("SW1", 13), "R13": ("SW2", -13), "D74": ("SW2", 13)}
R_BUTTON_PARTS = 16.6
R_TP = 16.9
R_SPINE = 8.15          # VDD spine arc on F.Cu, outside every centre part
Q1_ANGLE, Q1_R = 345.0, 6.9   # Q1 sits in the spine's gap; VBAT comes straight in along 345 deg
R_VBAT_VIA = 16.2
R_CELL_KEEPOUT = 10.5    # no B.Cu tracks/pour under the CR2032 (007 board review #1)
R_GND_VIA_MAX = 6.7     # GND vias under the cell only below the minus cap


# ============================================================ boundary planning
def plan_boundaries(blocks, anodes):
    """Pick sector boundaries (minute + 0.5) for block anode links and spokes."""
    hour_plus = {(5 * h + 0.5) % 60 for h in range(12)}

    def zone(b, lo, hi):
        return lo <= b <= hi

    def bad_common(b, inner=True):
        # inner=True: the item reaches radii < 13.6 mm, where the battery tabs are
        tab = zone(b, 12.5, 17.5) or zone(b, 42.5, 47.5)
        return b in hour_plus or (tab and inner)

    def bad_outer(b, ra):   # In1 link from r = 18.2 down to ring radius ra
        return (bad_common(b, ra < 13.6) or b in (9.5, 10.5, 19.5, 20.5)
                or b >= 56.5 or b <= 3.5)

    used = set()
    links = {}
    for bi, blk in enumerate(blocks):
        mins = [i for k, i in blk if k == "m"]
        hrs = [i for k, i in blk if k == "h"]
        if mins:
            cands = [(mins[j] + 0.5) % 60 for j in range(len(mins) - 1)]
            cands = [b for b in cands if not bad_outer(b, ring_r(anodes[bi])) and b not in used]
            mid = len(cands) // 2
            cands = [c for _, c in sorted(enumerate(cands), key=lambda ic: abs(ic[0] - mid))]
            links[(bi, "m")] = cands[0]
            used.add(cands[0])
        if hrs:
            lo, hi = 30 * hrs[0], 30 * hrs[-1]
            cands = [m + 0.5 for m in range(60) if lo < 6 * (m + 0.5) < hi]
            cands = [b for b in cands if not bad_common(b) and b not in used
                     and b not in (9.5, 10.5, 19.5, 20.5)]
            cands.sort(key=lambda b: abs(6 * b - (lo + hi) / 2))
            links[(bi, "h")] = cands[0]
            used.add(cands[0])
    # spokes: 9 boundaries >= 2 apart, clustered around 250 deg (left)
    free = [m + 0.5 for m in range(60) if not bad_common(m + 0.5) and (m + 0.5) not in used
            and not zone(m + 0.5, 7.5, 22.5) and not (m + 0.5 >= 56.5 or m + 0.5 <= 3.5)]
    free.sort(key=lambda b: abs(6 * b - 250))
    spokes = []
    for b in free:
        if all(min(abs(b - s), 60 - abs(b - s)) >= 2 for s in spokes):
            spokes.append(b)
        if len(spokes) == 9:
            break
    assert len(spokes) == 9, spokes
    return links, sorted(spokes)


# ============================================================ router
class Router:
    STEP = 0.05

    def __init__(self, board, netcodes):
        self.b = board
        self.netcodes = netcodes
        self.names = {ni.GetNetCode(): name for name, ni in netcodes.items()} if netcodes else {}
        self.half = R_BOARD + 0.3
        self.n = int(round(2 * self.half / self.STEP)) + 1
        self.occ = np.zeros((4, self.n, self.n), np.int32)   # inflated copper, -1 = blocked
        self.cu = np.zeros((4, self.n, self.n), np.int32)    # exact copper
        ys, xs = np.mgrid[0:self.n, 0:self.n]
        self.gx = (CX - self.half) + xs * self.STEP
        self.gy = (CY - self.half) + ys * self.STEP
        rr = np.hypot(self.gx - CX, self.gy - CY)
        self.rr = rr
        self.guard = np.zeros((self.n, self.n), bool)    # F.Cu kept for GUARD_NETS only
        self.resv = np.zeros((self.n, self.n), np.int32)  # F.Cu escape lanes: net code that owns the cell
        self.occ[:, rr > R_BOARD - 0.35 - TRACK / 2] = -1
        self.infl = CLEAR + TRACK / 2      # occupancy is inflated for the narrowest track
        self.holes = np.zeros((self.n, self.n), bool)   # where a new via hole would be too close to a hole

    def idx(self, x, y):
        return (int(round((y - (CY - self.half)) / self.STEP)), int(round((x - (CX - self.half)) / self.STEP)))

    def xy(self, i, j):
        return ((CX - self.half) + j * self.STEP, (CY - self.half) + i * self.STEP)

    def _window(self, x0, y0, x1, y1):
        i0, j0 = self.idx(x0, y0)
        i1, j1 = self.idx(x1, y1)
        i0, j0 = max(i0 - 1, 0), max(j0 - 1, 0)
        i1, j1 = min(i1 + 2, self.n), min(j1 + 2, self.n)
        return slice(i0, i1), slice(j0, j1)

    def _apply(self, layer, sl, mask, net):
        for arr, m in ((self.occ, mask[0]), (self.cu, mask[1])):
            cur = arr[layer][sl]
            arr[layer][sl] = np.where(m, np.where((cur == 0) | (cur == net), net, -1), cur)

    def mark_poly_fn(self, layer, net, bbox, fn):
        """fn(gx, gy, inflate) -> bool mask."""
        x0, y0, x1, y1 = bbox
        e = self.infl + 0.05
        sl = self._window(x0 - e, y0 - e, x1 + e, y1 + e)
        gx, gy = self.gx[sl], self.gy[sl]
        self._apply(layer, sl, (fn(gx, gy, self.infl), fn(gx, gy, 0.0)), net)

    def mark_circle(self, layer, net, x, y, r):
        self.mark_poly_fn(layer, net, (x - r, y - r, x + r, y + r),
                          lambda gx, gy, inf: (gx - x) ** 2 + (gy - y) ** 2 <= (r + inf) ** 2)

    def mark_seg(self, layer, net, x0, y0, x1, y1, w):
        def fn(gx, gy, inf):
            dx, dy = x1 - x0, y1 - y0
            L2 = dx * dx + dy * dy or 1e-9
            t = np.clip(((gx - x0) * dx + (gy - y0) * dy) / L2, 0, 1)
            return (gx - x0 - t * dx) ** 2 + (gy - y0 - t * dy) ** 2 <= (w / 2 + inf) ** 2
        self.mark_poly_fn(layer, net, (min(x0, x1) - w, min(y0, y1) - w, max(x0, x1) + w, max(y0, y1) + w), fn)

    def mark_rect(self, layer, net, x, y, w, h, ang):
        a = math.radians(ang)
        c, s = math.cos(a), math.sin(a)
        R = math.hypot(w, h) / 2

        def fn(gx, gy, inf):
            dx, dy = gx - x, gy - y
            u = dx * c - dy * s
            v = dx * s + dy * c
            return (np.abs(u) <= w / 2 + inf) & (np.abs(v) <= h / 2 + inf)
        self.mark_poly_fn(layer, net, (x - R, y - R, x + R, y + R), fn)

    def mark_hole(self, x, y, r=VIA_DRILL / 2):
        rr = r + VIA_DRILL / 2 + 0.26    # min hole-to-hole 0.25 mm
        sl = self._window(x - rr, y - rr, x + rr, y + rr)
        self.holes[sl] |= (self.gx[sl] - x) ** 2 + (self.gy[sl] - y) ** 2 <= rr ** 2

    def reserve_lanes(self, fp, length=1.0):
        """Keep a lane straight out of every connected pad of a fine-pitch part for its own net."""
        fx, fy = tomm(fp.GetPosition())
        for p in fp.Pads():
            code = p.GetNetCode()
            if not code or not p.IsOnLayer(pn.F_Cu):
                continue
            x, y = tomm(p.GetPosition())
            dx, dy = x - fx, y - fy
            if abs(dx) < 0.3 and abs(dy) < 0.3:
                continue            # exposed pad
            sz = p.GetSize(pn.F_Cu)
            w, h = pn.ToMM(sz.x), pn.ToMM(sz.y)
            if p.GetOrientation().AsDegrees() % 180 == 90:
                w, h = h, w
            if abs(dx) >= abs(dy):   # pad on the left/right side: lane runs along x
                sx = 1 if dx > 0 else -1
                xa, xb = sorted((x + sx * w / 2, x + sx * (w / 2 + length)))
                ya, yb = y - h / 2, y + h / 2
            else:
                sy = 1 if dy > 0 else -1
                ya, yb = sorted((y + sy * h / 2, y + sy * (h / 2 + length)))
                xa, xb = x - w / 2, x + w / 2
            m = (self.gx >= xa) & (self.gx <= xb) & (self.gy >= ya) & (self.gy <= yb)
            self.resv[m & (self.resv == 0)] = code

    def mark_board(self):
        """Rasterise every pad, track and via already on the board."""
        for fp in self.b.GetFootprints():
            for p in fp.Pads():
                net = p.GetNetCode() or -1   # unconnected pads block everything
                x, y = tomm(p.GetPosition())
                for li, L in enumerate(LAYERS):
                    if not p.IsOnLayer(L):
                        continue
                    sz = p.GetSize(L)
                    w, h = pn.ToMM(sz.x), pn.ToMM(sz.y)
                    if p.GetShape(L) == pn.PAD_SHAPE_CIRCLE:
                        self.mark_circle(li, net, x, y, w / 2)
                    else:
                        self.mark_rect(li, net, x, y, w, h, p.GetOrientation().AsDegrees())
                if p.HasHole():
                    self.mark_hole(x, y, pn.ToMM(p.GetDrillSize().x) / 2)
                if p.GetAttribute() == pn.PAD_ATTRIB_NPTH:
                    for li in range(4):
                        self.mark_circle(li, -1, x, y, pn.ToMM(p.GetDrillSize().x) / 2 + 0.1)
        for t in self.b.GetTracks():
            self.mark_item(t)

    def mark_item(self, t):
        net = t.GetNetCode()
        if isinstance(t, pn.PCB_VIA):
            x, y = tomm(t.GetPosition())
            for li in range(4):
                self.mark_circle(li, net, x, y, VIA_D / 2)
            self.mark_hole(x, y)
            return
        li = LAYERS.index(t.GetLayer())
        w = pn.ToMM(t.GetWidth())
        if isinstance(t, pn.PCB_ARC):
            c = t.GetCenter()
            cx, cy = tomm(c)
            r = pn.ToMM(t.GetRadius())
            a0 = math.atan2(pn.ToMM(t.GetStart().y) - cy, pn.ToMM(t.GetStart().x) - cx)
            a1 = math.atan2(pn.ToMM(t.GetEnd().y) - cy, pn.ToMM(t.GetEnd().x) - cx)
            am = math.atan2(pn.ToMM(t.GetMid().y) - cy, pn.ToMM(t.GetMid().x) - cx)
            # walk from a0 to a1 through am
            span = (a1 - a0) % (2 * math.pi)
            if (am - a0) % (2 * math.pi) > span:
                span -= 2 * math.pi
            n = max(4, int(abs(span) * r / 0.3))
            pts = [(cx + r * math.cos(a0 + span * k / n), cy + r * math.sin(a0 + span * k / n)) for k in range(n + 1)]
            for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
                self.mark_seg(li, net, xa, ya, xb, yb, w)
            return
        (x0, y0), (x1, y1) = tomm(t.GetStart()), tomm(t.GetEnd())
        self.mark_seg(li, net, x0, y0, x1, y1, w)

    # --------------------------------------------------------------- search
    @staticmethod
    def erode(mask, r):
        """True where a disk of radius r cells around the cell is all True (2-D)."""
        if r <= 0:
            return mask
        H, W = mask.shape
        acc = mask.copy()
        for di in range(-r, r + 1):
            for dj in range(-r, r + 1):
                if di * di + dj * dj > r * r:
                    continue
                sh = np.zeros_like(mask)
                si = slice(max(di, 0), H + min(di, 0))
                ti = slice(max(-di, 0), H + min(-di, 0))
                sj = slice(max(dj, 0), W + min(dj, 0))
                tj = slice(max(-dj, 0), W + min(-dj, 0))
                sh[ti, tj] = mask[si, sj]
                acc &= sh
        return acc

    def route(self, net, src_cells, goal_mask_fn, layers, bbox, via_cost=25.0, width=TRACK, max_pops=600000):
        """A* from src cells to any cell where goal_mask_fn(layer, i, j) is true."""
        (i0, j0), (i1, j1) = self.idx(bbox[0], bbox[1]), self.idx(bbox[2], bbox[3])
        i0, j0 = max(i0, 0), max(j0, 0)
        i1, j1 = min(i1, self.n - 1), min(j1, self.n - 1)
        H, W = i1 - i0 + 1, j1 - j0 + 1
        occ = self.occ[:, i0:i1 + 1, j0:j1 + 1]
        free = (occ == 0) | (occ == net)
        # via allowed where a disk of (VIA_D/2 + CLEAR - infl) is free on every layer
        rv = int(math.ceil((VIA_D / 2 + CLEAR - self.infl) / self.STEP))
        vok = self.erode(free.all(axis=0), rv) & ~self.holes[i0:i1 + 1, j0:j1 + 1]
        # cell safety (007 board review #1): no B.Cu tracks under the cell; VBAT/VDD vias never
        # under the cell; GND vias only under its minus cap. Other nets are current-limited.
        rw = self.rr[i0:i1 + 1, j0:j1 + 1]
        name = self.names.get(net, "")
        free[LB] &= rw > R_CELL_KEEPOUT + self.infl
        outside = rw > R_CELL_KEEPOUT + VIA_D / 2 + CLEAR
        if name in ("VBAT", "VDD"):
            vok &= outside
        elif name == "GND":
            vok &= outside | (rw < R_GND_VIA_MAX - VIA_D / 2)
        if name not in GUARD_NETS:
            free[LF] &= ~self.guard[i0:i1 + 1, j0:j1 + 1]
        if name == "VDD":   # VDD reaches the MCU only at pin 4 / C1; it must not wall in the other pins
            gxw, gyw = self.gx[i0:i1 + 1, j0:j1 + 1] - CX, self.gy[i0:i1 + 1, j0:j1 + 1] - CY
            band = (np.abs(gxw) < 3.3) & (np.abs(gyw) < 3.3)
            pin4 = (gxw > -4.7) & (gxw < -1.4) & (np.abs(gyw - 0.1) < 0.55)
            free[LF] &= ~band | pin4 | (self.cu[LF, i0:i1 + 1, j0:j1 + 1] == net)
        rv_ = self.resv[i0:i1 + 1, j0:j1 + 1]
        free[LF] &= (rv_ == 0) | (rv_ == net)
        ew = int(math.ceil((width / 2 - TRACK / 2) / self.STEP - 1e-9))
        if ew > 0:
            for L in range(4):
                free[L] = self.erode(free[L], ew) | (occ[L] == net) & (self.cu[L, i0:i1 + 1, j0:j1 + 1] == net)
        goal = np.zeros_like(free)
        for L in range(4):
            goal[L] = goal_mask_fn(L, slice(i0, i1 + 1), slice(j0, j1 + 1))
        freel = free.tolist()
        goall = goal.tolist()
        vokl = vok.tolist()
        gi = np.argwhere(goal)
        if len(gi) == 0:
            return None
        gc = gi[:, 1:].mean(axis=0)
        start = []
        for (L, i, j) in src_cells:
            if L in layers and i0 <= i <= i1 and j0 <= j <= j1 and freel[L][i - i0][j - j0]:
                start.append((L, i - i0, j - j0))
        if not start:
            return None

        def hfun(i, j):
            di, dj = abs(i - gc[0]), abs(j - gc[1])
            return 0.7 * (max(di, dj) + 0.414 * min(di, dj))
        dist = {}
        prev = {}
        pq = []
        for s in start:
            dist[s] = 0.0
            heapq.heappush(pq, (hfun(s[1], s[2]), 0.0, s))
        lcost = {LF: 1.0, LIN1: 1.6, LIN2: 1.15, LB: 1.1}
        moves = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
                 (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
        found = None
        pops = 0
        while pq:
            f, g, s = heapq.heappop(pq)
            if g > dist.get(s, 1e18):
                continue
            L, i, j = s
            if goall[L][i][j] and s not in start:
                found = s
                break
            pops += 1
            if pops > max_pops:
                break
            for di, dj, c in moves:
                ni, nj = i + di, j + dj
                if 0 <= ni < H and 0 <= nj < W and freel[L][ni][nj]:
                    t = (L, ni, nj)
                    ng = g + c * lcost[L]
                    if ng < dist.get(t, 1e18):
                        dist[t] = ng
                        prev[t] = s
                        heapq.heappush(pq, (ng + hfun(ni, nj), ng, t))
            if vokl[i][j]:
                for L2 in layers:
                    if L2 != L and freel[L2][i][j]:
                        t = (L2, i, j)
                        ng = g + via_cost
                        if ng < dist.get(t, 1e18):
                            dist[t] = ng
                            prev[t] = s
                            heapq.heappush(pq, (ng + hfun(i, j), ng, t))
        if not found:
            return None
        path = [found]
        while path[-1] in prev:
            path.append(prev[path[-1]])
        path.reverse()
        return [(L, i + i0, j + j0) for L, i, j in path]

    def commit(self, net, path, width=TRACK):
        """Turn a grid path into tracks and vias on the board."""
        items = []
        run = [path[0]]

        def flush(run):
            if len(run) < 2:
                return
            pts = [run[0]]
            for a, b, c in zip(run, run[1:], run[2:]):
                if (b[1] - a[1], b[2] - a[2]) != (c[1] - b[1], c[2] - b[2]):
                    pts.append(b)
            pts.append(run[-1])
            for a, b in zip(pts, pts[1:]):
                t = pn.PCB_TRACK(self.b)
                t.SetStart(V(*self.xy(a[1], a[2])))
                t.SetEnd(V(*self.xy(b[1], b[2])))
                t.SetWidth(mm(width))
                t.SetLayer(LAYERS[a[0]])
                t.SetNetCode(net)
                self.b.Add(t)
                items.append(t)
        for a, b in zip(path, path[1:]):
            if a[0] != b[0]:
                flush(run)
                v = pn.PCB_VIA(self.b)
                v.SetPosition(V(*self.xy(a[1], a[2])))
                v.SetWidth(pn.F_Cu, mm(VIA_D))
                v.SetDrill(mm(VIA_DRILL))
                v.SetNetCode(net)
                self.b.Add(v)
                items.append(v)
                run = [b]
            else:
                run.append(b)
        flush(run)
        for it in items:
            self.mark_item(it)
        return items

    def pad_cells(self, pad, net):
        x, y = tomm(pad.GetPosition())
        cells = []
        for li, L in enumerate(LAYERS):
            if not pad.IsOnLayer(L):
                continue
            sz = pad.GetSize(L)
            w, h = pn.ToMM(sz.x), pn.ToMM(sz.y)
            a = math.radians(pad.GetOrientation().AsDegrees())
            R = math.hypot(w, h) / 2
            (ia, ja), (ib, jb) = self.idx(x - R, y - R), self.idx(x + R, y + R)
            for i in range(ia, ib + 1):
                for j in range(ja, jb + 1):
                    gx, gy = self.xy(i, j)
                    dx, dy = gx - x, gy - y
                    u = dx * math.cos(a) - dy * math.sin(a)
                    v = dx * math.sin(a) + dy * math.cos(a)
                    circ = pad.GetShape(L) == pn.PAD_SHAPE_CIRCLE
                    if (dx * dx + dy * dy <= (w / 2 - 0.05) ** 2) if circ else (abs(u) <= w / 2 - 0.05 and abs(v) <= h / 2 - 0.05):
                        cells.append((li, i, j))
        return cells


# ============================================================ board build
def build_board(parts, assign, sch_root, out_path, order=None):
    mins, hours, anodes, blocks = assign
    b = pn.BOARD()
    b.SetCopperLayerCount(4)
    ds = b.GetDesignSettings()
    ds.SetBoardThickness(mm(1.0))
    ds.m_MinClearance = mm(0.1)
    ds.m_TrackMinWidth = mm(0.1)
    ds.m_ViasMinSize = mm(0.45)
    ds.m_MinThroughDrill = mm(0.2)
    ds.m_HoleToHoleMin = mm(0.25)
    ds.m_CopperEdgeClearance = mm(0.3)
    ds.m_HoleClearance = mm(0.2)
    nc = ds.m_NetSettings.GetDefaultNetclass()
    nc.SetClearance(mm(CLEAR))
    nc.SetTrackWidth(mm(TRACK))
    nc.SetViaDiameter(mm(VIA_D))
    nc.SetViaDrill(mm(VIA_DRILL))

    nets = {}

    def net(name, raw=False):
        if name not in nets:
            ni = pn.NETINFO_ITEM(b, name if raw else "/" + name)
            b.Add(ni)
            nets[name] = ni
        return nets[name]

    fps = {}

    def load(p):
        lib, name = p["fp"].split(":")
        path = os.path.join(PROJ, f"{NAME}.pretty") if lib == NAME else f"{KF}/{lib}.pretty"
        f = pn.FootprintLoad(path, name)
        f.SetFPID(pn.LIB_ID(lib, name))
        f.SetReference(p["ref"])
        f.SetValue(p["value"])
        f.SetPath(pn.KIID_PATH("/" + p["sym_uuid"]))
        f.SetSheetname("Root")
        f.SetSheetfile(f"{NAME}.kicad_sch")
        if p.get("dnp"):
            f.SetAttributes(f.GetAttributes() | pn.FP_DNP | pn.FP_EXCLUDE_FROM_POS_FILES)
        if p["kind"] == "TP":
            f.SetAttributes(f.GetAttributes() | pn.FP_EXCLUDE_FROM_BOM | pn.FP_EXCLUDE_FROM_POS_FILES)
        # dense board: no silkscreen on parts (JLC places from the CPL file); refs stay on Fab
        f.Reference().SetVisible(False)
        f.Value().SetVisible(False)
        for it in f.GraphicalItems():
            if it.GetLayer() == pn.F_SilkS:
                it.SetLayer(pn.F_Fab)
            elif it.GetLayer() == pn.B_SilkS:
                it.SetLayer(pn.B_Fab)
        b.Add(f)
        fps[p["ref"]] = f
        return f

    def setnets(f, p):
        for pad in f.Pads():
            n = p["pins"].get(pad.GetNumber())
            if n:
                pad.SetNet(net(n))
            elif pad.GetNumber() in p.get("nc_nets", {}):
                pad.SetNet(net(p["nc_nets"][pad.GetNumber()], raw=True))

    def place(f, x, y, deg, bottom=False):
        f.SetPosition(V(x, y))
        if bottom:
            f.Flip(f.GetPosition(), pn.FLIP_DIRECTION_LEFT_RIGHT)
        f.SetOrientationDegrees(deg)

    byref = {p["ref"]: p for p in parts}
    # ---- LEDs
    for p in parts:
        if p["kind"] in ("LED_M", "LED_H"):
            f = load(p)
            if "minute" in p:
                phi = 6 * p["minute"]
                place(f, *polar(R_MIN_LED, phi), -phi)
            else:
                phi = 30 * p["hour"]
                place(f, *polar(R_HOUR_LED, phi), 180 - phi)
            setnets(f, p)

    links, spokes = plan_boundaries(blocks, anodes)

    # ---- spokes and line resistors: line order around the arc follows the MCU pin order
    pin_order = ["2", "5", "6", "7", "8", "9", "10", "11", "12"]
    line_of_pin = {n: int(D.MCU_PINS[n][1]) for n in pin_order}
    # MCU pin 1, then pins 5-6 (left, below VCC/GND) and 7-12 (bottom) = decreasing clock angle
    spoke_for_line = {}
    for bnd, n in zip(sorted(spokes, reverse=True), pin_order):
        spoke_for_line[line_of_pin[n]] = bnd
    for k in range(D.N_LINES):
        p = byref[f"R{k+1}"]
        f = load(p)
        phi = 6 * spoke_for_line[k]
        place(f, *polar(R_RES, phi), 90 - phi)
        setnets(f, p)
    # ---- centre parts
    for ref, (dx, dy, rot) in INNER.items():
        p = byref[ref]
        f = load(p)
        place(f, CX + dx, CY + dy, rot)
        setnets(f, p)
    # Q1: drain (pad 3) pointing straight out, so VBAT can come in radially along Q1_ANGLE
    p = byref["Q1"]
    f = load(p)
    best = None
    for th in range(0, 360, 1):
        place(f, *polar(Q1_R, Q1_ANGLE), th)
        d3 = [q for q in f.Pads() if q.GetNumber() == "3"][0]
        x3, y3 = tomm(d3.GetPosition())
        score = math.hypot(x3 - CX, y3 - CY) - abs(((clock_deg(x3, y3) - Q1_ANGLE + 180) % 360) - 180)
        if best is None or score > best[0]:
            best = (score, th)
    place(f, *polar(Q1_R, Q1_ANGLE), best[1])
    setnets(f, p)
    # ---- bottom: battery, buttons, test pads
    p = byref["BT1"]
    f = load(p)
    place(f, CX, CY, 0, bottom=True)
    setnets(f, p)
    for ref, phi in BUTTONS.items():
        p = byref[ref]
        f = load(p)
        place(f, *polar(R_BUTTON, phi), -phi, bottom=True)
        setnets(f, p)
        # plunger must face outwards: ground pad 3 nearer the centre than pads 1/2
        pads = {q.GetNumber(): q for q in f.Pads()}
        r3 = math.hypot(*[a - c for a, c in zip(tomm(pads["3"].GetPosition()), (CX, CY))])
        r1 = math.hypot(*[a - c for a, c in zip(tomm(pads["1"].GetPosition()), (CX, CY))])
        if r3 > r1:
            f.SetOrientationDegrees(180 - phi)
    for ref, (sw, dphi) in BUTTON_PARTS.items():
        p = byref[ref]
        f = load(p)
        phi = BUTTONS[sw] + dphi
        place(f, *polar(R_BUTTON_PARTS, phi), 90 + phi, bottom=True)
        setnets(f, p)
    for ref, off in TESTPADS.items():
        p = byref[ref]
        f = load(p)
        place(f, CX + off, CY - R_TP, 0, bottom=True)   # straight 2.54 mm row for a pogo strip
        setnets(f, p)

    # ---- explicit copper
    def track(pts, name, layer, w=TRACK):
        for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
            t = pn.PCB_TRACK(b)
            t.SetStart(V(xa, ya))
            t.SetEnd(V(xb, yb))
            t.SetWidth(mm(w))
            t.SetLayer(layer)
            t.SetNet(net(name))
            b.Add(t)

    def arc(r, deg0, deg1, name, layer, w=TRACK):
        # split into pieces <= 90 deg
        n = max(1, int(math.ceil(abs(deg1 - deg0) / 90)))
        for k in range(n):
            a0 = deg0 + (deg1 - deg0) * k / n
            a1 = deg0 + (deg1 - deg0) * (k + 1) / n
            t = pn.PCB_ARC(b)
            t.SetStart(V(*polar(r, a0)))
            t.SetMid(V(*polar(r, (a0 + a1) / 2)))
            t.SetEnd(V(*polar(r, a1)))
            t.SetWidth(mm(w))
            t.SetLayer(layer)
            t.SetNet(net(name))
            b.Add(t)

    def via(x, y, name):
        v = pn.PCB_VIA(b)
        v.SetPosition(V(x, y))
        v.SetWidth(pn.F_Cu, mm(VIA_D))
        v.SetDrill(mm(VIA_DRILL))
        v.SetNet(net(name))
        b.Add(v)

    def dot(x, y, r=0.1):
        s = pn.PCB_SHAPE(b)
        s.SetShape(pn.SHAPE_T_CIRCLE)
        s.SetCenter(V(x, y))
        s.SetEnd(V(x + r, y))
        s.SetFilled(True)
        s.SetWidth(mm(0.05))
        s.SetLayer(pn.F_SilkS)
        b.Add(s)

    def pad_xy(ref, num):
        return tomm([q for q in fps[ref].Pads() if q.GetNumber() == num][0].GetPosition())

    # rings on In2
    for k in range(D.N_LINES):
        arc(ring_r(k), 0, 360, f"L{k}", pn.In2_Cu, 0.2)
    # minute LEDs: cathode trace + via, anode stub
    for m in range(60):
        a, c = mins[m]
        ref = f"D{m+1}"
        phi = 6 * m
        kx, ky = pad_xy(ref, "1")
        ka = clock_deg(kx, ky)
        rc = ring_r(c)
        track([(kx, ky), polar(16.6, ka), polar(16.1, phi), polar(rc, phi)], f"L{c}", pn.F_Cu)
        dot(*polar(16.72, ka))      # cathode mark (007 review #11)
        via(*polar(rc, phi), f"L{c}")
        ax, ay = pad_xy(ref, "2")
        track([(ax, ay), polar(R_ARC_OUT, clock_deg(ax, ay))], f"L{a}", pn.F_Cu)
    # hour LEDs
    for h in range(12):
        a, c = hours[h]
        ref = f"D{61+h}"
        phi = 30 * h
        kx, ky = pad_xy(ref, "1")
        rc = ring_r(c)

        def off(r):
            return phi + math.degrees(math.asin(HOUR_VIA_OFF / r))
        track([(kx, ky), polar(10.2, clock_deg(kx, ky)), polar(10.45, off(10.45)), polar(rc, off(rc))],
              f"L{c}", pn.F_Cu)
        via(*polar(rc, off(rc)), f"L{c}")
        ax, ay = pad_xy(ref, "2")
        track([(ax, ay), polar(R_ARC_IN, clock_deg(ax, ay))], f"L{a}", pn.F_Cu)
        dot(*polar(10.35, clock_deg(kx, ky)))   # cathode mark
    # anode arcs and their links to the rings (links run on B.Cu)
    for bi, blk in enumerate(blocks):
        a = anodes[bi]
        mins_b = [i for k, i in blk if k == "m"]
        hrs_b = [i for k, i in blk if k == "h"]
        if mins_b:
            angs = []
            for m in mins_b:
                ax, ay = pad_xy(f"D{m+1}", "2")
                angs.append(clock_deg(ax, ay))
            base = angs[0]
            angs = [base + ((x - base) % 360) for x in angs]
            arc(R_ARC_OUT, min(angs), max(angs), f"L{a}", pn.F_Cu)
            bnd = links[(bi, "m")]
            ang = 6 * bnd
            via(*polar(R_ARC_OUT, ang), f"L{a}")
            # on In1 (GND plane layer), so nothing on the bottom side can collide with it
            track([polar(R_ARC_OUT, ang), polar(ring_r(a), ang)], f"L{a}", pn.In1_Cu)
            via(*polar(ring_r(a), ang), f"L{a}")
        if hrs_b:
            angs = []
            for h in hrs_b:
                ax, ay = pad_xy(f"D{61+h}", "2")
                angs.append(clock_deg(ax, ay))
            base = angs[0]
            angs = [base + ((x - base) % 360) for x in angs]
            arc(R_ARC_IN, min(angs), max(angs), f"L{a}", pn.F_Cu)
            bnd = links[(bi, "h")]
            ang = 6 * bnd
            via(*polar(R_ARC_IN, ang), f"L{a}")
            track([polar(R_ARC_IN, ang), polar(ring_r(a), ang)], f"L{a}", pn.In1_Cu)   # not B.Cu: under the cell
            via(*polar(ring_r(a), ang), f"L{a}")
    # spokes on In1 + resistor stubs on F.Cu
    for k, bnd in spoke_for_line.items():
        ang = 6 * bnd
        via(*polar(R_SPOKE_IN, ang), f"L{k}")
        track([polar(R_SPOKE_IN, ang), polar(ring_r(k), ang)], f"L{k}", pn.In1_Cu, 0.2)
        via(*polar(ring_r(k), ang), f"L{k}")
        track([pad_xy(f"R{k+1}", "2"), polar(R_SPOKE_IN, ang)], f"L{k}", pn.F_Cu, 0.2)
    # accelerometer CS + SA0 (both VDD) sit between SCL and SDA. A VDD via there would be under the
    # cell, so instead SCL and SDA drop to the inner layers at their pads (signal vias), which leaves
    # F.Cu free for VDD to reach CS/SA0 from the left.
    (x1, y1), (x2, y2), (x3, y3), (x4, y4) = [pad_xy("U2", n) for n in "1234"]
    ux, uy = tomm(fps["U2"].GetPosition())
    d = 1 if x2 > ux else -1            # side of U2 that carries pins 1-4
    vx = x2 + d * 0.75
    track([(x2, y2), (vx, y2)], "VDD", pn.F_Cu, 0.15)
    track([(x3, y3), (vx, y3)], "VDD", pn.F_Cu, 0.15)
    track([(vx, y2), (vx, y3), (vx + d * 0.5, (y2 + y3) / 2)], "VDD", pn.F_Cu, 0.15)
    sclv = (x1 + d * 0.8, y1 + (0.45 if y1 > uy else -0.45))
    sdav = (x4 + d * 0.8, y4 + (0.45 if y4 > uy else -0.45))
    track([(x1, y1), sclv], "SCL", pn.F_Cu, 0.15)
    via(*sclv, "SCL")
    track([(x4, y4), sdav], "SDA", pn.F_Cu, 0.15)
    via(*sdav, "SDA")
    PREROUTED["VDD"] = [(("U2", "2"), ("U2", "3")), (vx + d * 0.5, (y2 + y3) / 2), (LF,)]
    PREROUTED["SCL"] = [(("U2", "1"),), sclv, (LF, LIN1, LIN2, LB)]
    PREROUTED["SDA"] = [(("U2", "4"),), sdav, (LF, LIN1, LIN2, LB)]
    # crystal guard: only XT1/XT2/GND copper on F.Cu around Y1 (007 board review #6)
    guard_box = courtyard_box(fps["Y1"], 0.5)
    # VDD spine (007 board review #1 follow-up): VDD may not use vias under the cell, so it runs on
    # F.Cu as an arc outside all centre parts; every VDD pin connects outwards to it. It has a gap
    # at Q1, where VBAT comes in from outside the cell along a free sector boundary.
    # drawn as short segments so the unused ends can be trimmed after routing
    for a0, a1 in ((268, Q1_ANGLE - 12), (Q1_ANGLE + 12, 462)):
        n = int(math.ceil((a1 - a0) * math.pi / 180 * R_SPINE / 0.3))
        track([polar(R_SPINE, a0 + (a1 - a0) * k / n) for k in range(n + 1)], "VDD", pn.F_Cu)
    (qx, qy) = pad_xy("Q1", "3")
    track([(qx, qy), polar(R_VBAT_VIA, Q1_ANGLE)], "VBAT", pn.F_Cu, 0.2)
    via(*polar(R_VBAT_VIA, Q1_ANGLE), "VBAT")
    PREROUTED["VBAT"] = [(("Q1", "3"),), polar(R_VBAT_VIA, Q1_ANGLE), (LF, LIN1, LIN2, LB)]
    EXTRA_TERMS["VDD"] = [[polar(R_SPINE, a / 10) for a in range(2680, int((Q1_ANGLE - 12) * 10), 5)],
                          [polar(R_SPINE, a / 10) for a in range(int((Q1_ANGLE + 12) * 10), 4620, 5)]]
    # battery minus pad: four vias down into the GND planes
    for dx in (-0.6, 0.6):          # inside the MCU exposed pad (GND) - also the cell's minus pad
        for dy in (-0.6, 0.6):
            via(CX + dx, CY + dy, "GND")

    # ---- board outline + silkscreen
    s = pn.PCB_SHAPE(b)
    s.SetShape(pn.SHAPE_T_CIRCLE)
    s.SetCenter(V(CX, CY))
    s.SetEnd(V(CX + R_BOARD, CY))
    s.SetLayer(pn.Edge_Cuts)
    s.SetWidth(mm(0.05))
    b.Add(s)
    for txt, (x, y), lay, sz in [("LED WATCH rev A", (CX, CY + 12.6), pn.B_SilkS, 0.8)]:
        t = pn.PCB_TEXT(b)
        t.SetText(txt)
        t.SetPosition(V(x, y))
        t.SetLayer(lay)
        t.SetTextSize(V(sz, sz))
        t.SetTextThickness(mm(sz * 0.15))
        if lay == pn.B_SilkS:
            t.SetMirrored(True)
        b.Add(t)

    # ---- route the rest
    rt = Router(b, nets)
    rt.mark_board()
    for dx_, dy_ in ((1.9, 0), (-1.9, 0), (0, 1.9), (0, -1.9)):   # pad-2 paste dots: no via there (007 N1)
        rt.mark_hole(CX + dx_, CY + dy_, 0.5 + 0.1 - VIA_DRILL / 2 - 0.26 + VIA_D / 2)
    rt.reserve_lanes(fps["U1"])
    rt.reserve_lanes(fps["U2"])
    gx0, gy0, gx1, gy1 = guard_box
    rt.guard |= (rt.gx >= gx0) & (rt.gx <= gx1) & (rt.gy >= gy0) & (rt.gy <= gy1)
    failures = route_all(b, rt, nets, fps, parts, order)

    # ---- GND planes
    ko = pn.ZONE(b)       # B.Cu keep-out under the cell: no tracks, no pour (vias/pads allowed)
    ko.SetIsRuleArea(True)
    ko.SetLayer(pn.B_Cu)
    ko.SetDoNotAllowTracks(True)
    ko.SetDoNotAllowCopperPour(True)
    ko.SetDoNotAllowVias(False)
    ko.SetDoNotAllowPads(False)
    ko.SetDoNotAllowFootprints(False)
    ko.SetZoneName("cell keep-out")
    o = ko.Outline()
    o.NewOutline()
    for k in range(72):
        x, y = polar(R_CELL_KEEPOUT, k * 5)
        o.Append(mm(x), mm(y))
    b.Add(ko)
    for layer, prio in ((pn.In1_Cu, 0), (pn.In2_Cu, 0), (pn.B_Cu, 0)):
        z = pn.ZONE(b)
        z.SetLayer(layer)
        z.SetNet(net("GND"))
        o = z.Outline()
        o.NewOutline()
        rz = R_BOARD - 0.3
        for k in range(72):
            x, y = polar(rz, k * 5)
            o.Append(mm(x), mm(y))
        z.SetMinThickness(mm(0.2))
        z.SetLocalClearance(mm(0.2))
        z.SetPadConnection(pn.ZONE_CONNECTION_FULL)
        z.SetThermalReliefGap(mm(0.2))
        z.SetThermalReliefSpokeWidth(mm(0.25))
        z.SetIslandRemovalMode(pn.ISLAND_REMOVAL_MODE_ALWAYS)
        z.SetAssignedPriority(prio)
        b.Add(z)
    pn.SaveBoard(out_path, b)
    b = pn.LoadBoard(out_path)
    clean_dangling(b)
    # vias under the cell keep no copper ring on layers they don't connect to (B.Cu in particular)
    for t in b.GetTracks():
        if t.Type() == pn.PCB_VIA_T and math.hypot(*(np.array(tomm(t.GetPosition())) - (CX, CY))) < 11.0:
            t.Padstack().SetUnconnectedLayerMode(pn.PADSTACK.UNCONNECTED_LAYER_MODE_REMOVE_ALL)
    pn.ZONE_FILLER(b).Fill(b.Zones())
    pn.SaveBoard(out_path, b)
    return failures, links, spoke_for_line


PREROUTED = {}   # net -> (pads already joined, point standing in for them, its layers)
EXTRA_TERMS = {}  # net -> list of F.Cu point lists (explicit copper the router must join, e.g. the VDD spine)
GUARD_NETS = ("XT1", "XT2", "GND")


def courtyard_box(fp, margin):
    xs, ys = [], []
    for it in fp.GraphicalItems():
        if it.GetLayer() in (pn.F_CrtYd, pn.B_CrtYd):
            bb = it.GetBoundingBox()
            xs += [pn.ToMM(bb.GetX()), pn.ToMM(bb.GetRight())]
            ys += [pn.ToMM(bb.GetY()), pn.ToMM(bb.GetBottom())]
    return min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin

# Pins that escape past the power tree go first (they claim their vias), then the rest, then
# VDD/VBAT, which may only use F.Cu under the cell and route round them.
DEFAULT_ORDER = (["L0_M", "TX", "RTC", "UPDI", "SW_A", "SW_B", "ACC_INT", "XT1", "XT2", "SCL", "SDA"]
                 + [f"L{k}_M" for k in range(1, D.N_LINES)] + ["VDD", "VBAT", "SW_A_K", "SW_B_K"])


class Term:
    """A routing terminal: a pad, or a via standing in for already-joined pads."""

    def __init__(self, pad, rt, code, xy=None, layers=(0, 1, 2, 3), pts=None):
        self.pad, self.rt, self.code, self.layers, self.pts = pad, rt, code, layers, pts
        if pts:
            xy = pts[len(pts) // 2]
        if pad is not None:
            self.x, self.y = tomm(pad.GetPosition())
            self.key = (pad.GetParentFootprint().GetReference(), pad.GetNumber())
        else:
            self.x, self.y = xy
            self.key = ("via", f"{xy[0]:.2f},{xy[1]:.2f}")

    def cells(self):
        if self.pts:
            return list({(LF,) + self.rt.idx(x, y) for x, y in self.pts})
        if self.pad is not None:
            return self.rt.pad_cells(self.pad, self.code)
        i, j = self.rt.idx(self.x, self.y)
        r = int((VIA_D / 2 - 0.05) / self.rt.STEP)
        return [(L, i + di, j + dj) for L in self.layers for di in range(-r, r + 1) for dj in range(-r, r + 1)
                if di * di + dj * dj <= r * r]


def clean_dangling(b):
    """Remove router stubs and the unused ends of the VDD spine: every track with a loose end goes,
    unless removing it would break a connection."""
    def unconnected():
        b.BuildConnectivity()
        c = b.GetConnectivity()
        c.RecalculateRatsnest()
        return c.GetUnconnectedCount(False), c
    for _ in range(400):
        base, conn = unconnected()
        cands = [t for t in b.GetTracks() if t.Type() == pn.PCB_TRACE_T and conn.TestTrackEndpointDangling(t, False)]
        removed = 0
        for t in cands:
            b.Remove(t)
            if unconnected()[0] > base:
                b.Add(t)
            else:
                removed += 1
        if not removed:
            break
    # a track still dangling is joined part-way along: cut its loose end back to the last junction
    b.BuildConnectivity()
    conn = b.GetConnectivity()
    for t in list(b.GetTracks()):
        if t.Type() != pn.PCB_TRACE_T or not conn.TestTrackEndpointDangling(t, False):
            continue
        s0, e0 = t.GetStart(), t.GetEnd()
        others = [o for o in conn.GetConnectedTracks(t)]
        def touches(a):
            for o in others:
                pts = [o.GetPosition()] if o.Type() == pn.PCB_VIA_T else [o.GetStart(), o.GetEnd()]
                if any((q - a).EuclideanNorm() < mm(0.02) for q in pts):
                    return True
            return any(p.HitTest(a) for p in conn.GetConnectedPads(t))
        ts, te = touches(s0), touches(e0)
        if ts == te:
            continue
        keep, loose = (s0, e0) if ts else (e0, s0)
        dx, dy = loose.x - keep.x, loose.y - keep.y
        L2 = float(dx * dx + dy * dy) or 1.0
        best = 0.0
        for o in others:
            for q in ([o.GetPosition()] if o.Type() == pn.PCB_VIA_T else [o.GetStart(), o.GetEnd()]):
                u = ((q.x - keep.x) * dx + (q.y - keep.y) * dy) / L2
                perp = abs((q.x - keep.x) * dy - (q.y - keep.y) * dx) / math.sqrt(L2)
                if 0 < u <= 1 and perp < t.GetWidth():
                    best = max(best, u)
        if best > 0:
            cut = pn.VECTOR2I(int(keep.x + dx * best), int(keep.y + dy * best))
            if ts:
                t.SetEnd(cut)
            else:
                t.SetStart(cut)


def route_all(b, rt, nets, fps, parts, order=None):
    """Connect every pad of every net that the explicit structure did not."""
    explicit = {f"L{k}" for k in range(D.N_LINES)}
    order = order or DEFAULT_ORDER
    pads_by_net = {}
    for fp in b.GetFootprints():
        for p in fp.Pads():
            n = p.GetNetname().lstrip("/")
            if n:
                pads_by_net.setdefault(n, []).append(p)
    failures = []
    sig_layers = (LF, LIN1, LIN2, LB)   # In1 (GND plane) only where nothing else gets through
    state = {}
    for name in order:
        code = nets[name].GetNetCode()
        pads = [Term(p, rt, code) for p in pads_by_net.get(name, [])]
        if name in PREROUTED:
            joined, (vx, vy), tl = PREROUTED[name]
            pads = [t for t in pads if t.key not in joined] + [Term(None, rt, code, (vx, vy), tl)]
        for pts in EXTRA_TERMS.get(name, []):
            pads.append(Term(None, rt, code, pts=pts))
        if len(pads) < 2:
            continue
        # explicit copper (e.g. the VDD spine) is the root of the tree, otherwise nearest the centre
        pads.sort(key=lambda t: (t.pts is None, math.hypot(t.x - CX, t.y - CY)))
        state[name] = (code, pads, pads[0].cells(), pads[1:])

    def connect(name, p, glob):
        code, pads, tree, _ = state[name]
        src = p.cells()
        xs = [q.x for q in pads]
        ys = [q.y for q in pads]
        m = 4.0
        bbox = (min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m)
        if glob:
            bbox = (CX - 19, CY - 19, CX + 19, CY + 19)
        tree_set = set(tree)

        def goal(L, si, sj):
            g = np.zeros((si.stop - si.start, sj.stop - sj.start), bool)
            for (l2, i, j) in tree_set:
                if l2 == L and si.start <= i < si.stop and sj.start <= j < sj.stop:
                    g[i - si.start, j - sj.start] = True
            return g
        w = TRACK   # VDD/VBAT carry ~5 mA; 0.15 mm keeps the F.Cu-only power tree narrow
        path = rt.route(code, src, goal, sig_layers, bbox, width=w, max_pops=4000000 if glob else 600000)
        if path is None:
            return False
        rt.commit(code, path, w)
        tree += src + path
        return True

    # pass 1: every connection inside its own bounding box; pass 2: anywhere
    pending = []
    for name in state:
        for p in state[name][3]:
            if not connect(name, p, False):
                pending.append((name, p))
    if pending:
        print("  pass 1 left:", [(n,) + p.key for n, p in pending], flush=True)
    for name, p in pending:
        if not connect(name, p, True):
            failures.append((name,) + p.key)
    # GND: every GND pad drops a via into the In1 plane (unless it is already big)
    code = nets["GND"].GetNetCode()
    for p in pads_by_net.get("GND", []):
        if p.GetParentFootprint().GetReference() == "BT1":
            continue
        src = rt.pad_cells(p, code)
        x, y = tomm(p.GetPosition())

        def goal(L, si, sj):
            if L == LIN1:
                return np.ones((si.stop - si.start, sj.stop - sj.start), bool)
            return (rt.cu[L][si, sj] == code) & (rt.cu[LIN1][si, sj] == code)
        layers = (LF, LIN1, LIN2, LB)
        path = rt.route(code, src, goal, layers, (x - 4, y - 4, x + 4, y + 4), via_cost=2.0, width=0.2)
        if path is None:   # under the cell GND vias must sit below the minus cap: search wider
            path = rt.route(code, src, goal, layers, (x - 9, y - 9, x + 9, y + 9), via_cost=2.0, width=0.2,
                            max_pops=2000000)
        if path is None:
            failures.append(("GND", p.GetParentFootprint().GetReference(), p.GetNumber()))
            continue
        rt.commit(code, path, 0.2)
    return failures
