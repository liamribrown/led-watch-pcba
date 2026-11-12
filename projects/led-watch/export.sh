#!/usr/bin/env bash
# Export the LED watch for JLCPCB with kicad-cli:
#   1. ERC + DRC (with schematic parity); any error stops the export
#   2. schematic PDF
#   3. 4-layer gerbers + Excellon drills, zipped
#   4. JLCPCB assembly files: BOM (Comment, Designator, Footprint, LCSC Part #) and
#      CPL (Designator, Mid X, Mid Y, Layer, Rotation); DNP parts and test pads left out
#   5. board geometry JSON for the 3D simulation (tools/export_3d.py; EXPORT_3D=0 skips it)
#   6. PNG previews of both sides (gerbv), if gerbv is installed
#
# Usage: export.sh [output-dir]
#   output-dir is relative to the directory you run it from; the default is output/ next to
#   this script (git-ignored). Set SKIP_CHECKS=1 to export even when ERC/DRC report errors.
# The KiCad files are generated: run tools/generate.py first if you changed the design.
set -euo pipefail

OUT=$(realpath -m -- "${1:-$(dirname "$0")/output}")
cd "$(dirname "$0")"
NAME=led-watch
SCH="$NAME.kicad_sch"
PCB="$NAME.kicad_pcb"
GERBER_DIR="$OUT/gerbers"
LAYERS="F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts"

command -v kicad-cli >/dev/null || { echo "kicad-cli not found: sudo apt install kicad" >&2; exit 1; }
echo "kicad-cli $(kicad-cli version)"

# kicad-cli alone never creates the per-user library tables; copy the stock ones if missing.
KICAD_CFG="${XDG_CONFIG_HOME:-$HOME/.config}/kicad/$(kicad-cli version | cut -d. -f1).0"
for table in sym-lib-table fp-lib-table; do
    if [[ ! -f "$KICAD_CFG/$table" && -f "/usr/share/kicad/template/$table" ]]; then
        mkdir -p "$KICAD_CFG"
        cp "/usr/share/kicad/template/$table" "$KICAD_CFG/$table"
        echo "note: created $KICAD_CFG/$table from the KiCad default"
    fi
done

rm -rf -- "${GERBER_DIR:?}"
mkdir -p "$OUT" "$GERBER_DIR"

check() {   # check <erc|drc|cell> <command...>
    local what=$1; shift
    if "$@" >/dev/null 2>&1; then
        echo "$what: OK (report: $OUT/$what.rpt)"
    elif [[ "${SKIP_CHECKS:-0}" == 1 ]]; then
        echo "$what: errors found, continuing because SKIP_CHECKS=1 (see $OUT/$what.rpt)" >&2
    else
        echo "$what: errors found, see $OUT/$what.rpt (set SKIP_CHECKS=1 to export anyway)" >&2
        cat "$OUT/$what.rpt" >&2
        exit 1
    fi
}
check erc kicad-cli sch erc --severity-error --exit-code-violations -o "$OUT/erc.rpt" "$SCH"
check drc kicad-cli pcb drc --severity-error --schematic-parity --exit-code-violations -o "$OUT/drc.rpt" "$PCB"
# 007 board review #1: no unsafe copper under the CR2032 (see tools/check_cell.py)
check cell sh -c 'python3 tools/check_cell.py "$1" > "$2" 2>/dev/null' _ "$PCB" "$OUT/cell.rpt"

kicad-cli sch export pdf -o "$OUT/$NAME-schematic.pdf" "$SCH" >/dev/null
echo "schematic: $OUT/$NAME-schematic.pdf"

kicad-cli pcb export gerbers -l "$LAYERS" --subtract-soldermask -o "$GERBER_DIR/" "$PCB" >/dev/null
kicad-cli pcb export drill --format excellon --excellon-separate-th \
    --generate-map --map-format gerberx2 -o "$GERBER_DIR/" "$PCB" >/dev/null
python3 -I -c 'import sys, zipfile, pathlib
d = pathlib.Path(sys.argv[1])
with zipfile.ZipFile(sys.argv[2], "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted(d.iterdir()): z.write(f, f.name)' "$GERBER_DIR" "$OUT/$NAME-gerbers.zip"
echo "gerbers: $(ls "$GERBER_DIR" | wc -l) files -> $OUT/$NAME-gerbers.zip"

# --- assembly files
kicad-cli sch export bom --fields 'Reference,Value,Footprint,LCSC,${QUANTITY}' \
    --labels 'Reference,Value,Footprint,LCSC,Qty' --group-by 'Value,Footprint,LCSC' \
    --ref-delimiter ',' --ref-range-delimiter '' \
    --exclude-dnp -o "$OUT/bom-kicad.csv" "$SCH" >/dev/null
kicad-cli pcb export pos --format csv --units mm --side both --exclude-dnp \
    -o "$OUT/pos-kicad.csv" "$PCB" >/dev/null
python3 -I - "$OUT" "$NAME" <<'PY'
import csv, re, sys
out, name = sys.argv[1], sys.argv[2]


def refs_of(cell):
    """Every designator in a BOM cell. JLCPCB wants full lists, never ranges like D1-D60."""
    refs = []
    for part in filter(None, (p.strip() for p in cell.split(","))):
        m = re.fullmatch(r"([A-Za-z]+)(\d+)-(?:[A-Za-z]+)?(\d+)", part)
        if m:
            refs += [f"{m.group(1)}{n}" for n in range(int(m.group(2)), int(m.group(3)) + 1)]
        else:
            refs.append(part)
    return refs

rows = list(csv.DictReader(open(f"{out}/bom-kicad.csv")))
missing = []
with open(f"{out}/{name}-bom-jlcpcb.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #", "Quantity"])
    for r in rows:
        if not r["LCSC"]:
            missing.append(r["Reference"])
        refs = refs_of(r["Reference"])
        if len(refs) != int(r["Qty"]):
            sys.exit(f"ERROR: BOM line {r['Value']}: {len(refs)} designators but quantity {r['Qty']}")
        w.writerow([r["Value"], ",".join(refs), r["Footprint"].split(":")[-1], r["LCSC"], r["Qty"]])
pos = list(csv.DictReader(open(f"{out}/pos-kicad.csv")))
# Rotation corrections for JLCPCB, by KiCad package and side: fill these in after checking
# JLCPCB's placement preview (007 board review #4). Parts to check there: SW1/SW2 (plunger must
# point outwards, not at the cell), U1 pin 1, U2 pin 1, Q1, D1 (cathode counter-clockwise),
# D61 (cathode clockwise), BT1. Example: ROT_FIX = {("SOT-23", "top"): 180}
ROT_FIX = {}
with open(f"{out}/{name}-cpl-jlcpcb.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    for r in pos:
        w.writerow([r["Ref"], f'{float(r["PosX"]):.4f}mm', f'{float(r["PosY"]):.4f}mm',
                    "Top" if r["Side"] == "top" else "Bottom",
                    f'{(float(r["Rot"]) + ROT_FIX.get((r["Package"], r["Side"]), 0)) % 360:.2f}'])
parts = sum(int(r["Qty"]) for r in rows)
top = sum(r["Side"] == "top" for r in pos)
print(f"bom: {len(rows)} lines, {parts} parts -> {out}/{name}-bom-jlcpcb.csv")
print(f"cpl: {len(pos)} placements ({top} top, {len(pos) - top} bottom) -> {out}/{name}-cpl-jlcpcb.csv")
if missing:
    sys.exit(f"ERROR: BOM lines without an LCSC number: {', '.join(missing)}")
bom_refs = [x for r in rows for x in refs_of(r["Reference"])]
cpl_refs = [r["Ref"] for r in pos]
if len(set(bom_refs)) != len(bom_refs) or set(bom_refs) != set(cpl_refs) or len(cpl_refs) != len(set(cpl_refs)):
    only_bom = sorted(set(bom_refs) - set(cpl_refs))
    only_cpl = sorted(set(cpl_refs) - set(bom_refs))
    sys.exit(f"ERROR: BOM and CPL designators differ (only in BOM: {only_bom}, only in CPL: {only_cpl})")
print(f"bom/cpl: the same {len(cpl_refs)} designators in both files")
PY

if command -v gerbv >/dev/null; then
    g="$GERBER_DIR/$NAME"
    for side in F B; do
        lc=$([[ $side == F ]] && echo F || echo B)
        ext_cu=$([[ $side == F ]] && echo gtl || echo gbl)
        ext_mask=$([[ $side == F ]] && echo gts || echo gbs)
        ext_silk=$([[ $side == F ]] && echo gto || echo gbo)
        if gerbv --export=png --dpi=600 --border=3 --background='#000000' --output="$OUT/$NAME-$side.png" \
               "$g-Edge_Cuts.gm1" "$g-${lc}_Cu.$ext_cu" "$g-${lc}_Mask.$ext_mask" "$g-${lc}_Silkscreen.$ext_silk" \
               "$g-PTH.drl" 2>/dev/null; then
            echo "preview: $OUT/$NAME-$side.png"
        fi
    done
fi
# optional: board geometry for the 3D browser simulation (set EXPORT_3D=0 to skip)
if [[ "${EXPORT_3D:-1}" == 1 ]]; then
    python3 tools/export_3d.py "$PCB" "$OUT/board-geometry.json" 2>/dev/null
fi
echo "done."
