"""DK-1 printed parts, parametric (CadQuery 2.x).

Run:  python parts.py      -> writes STEP + STL + SVG views into ./out/

Every dimension marked VERIFY comes from a datasheet drawing or is unpublished;
check it against the physical samples before ordering tooling.
"""
import cadquery as cq, os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

# ---- Aluminum profile: SuperLightingLED HL-BAPL004 (outer 17.6 x 15.8 mm, published) ----
PW, PH = 17.6, 15.8          # profile outer width / height  (published)
C = 0.30                     # slide-fit clearance per side (cap sleeves)
CJ = 0.15                    # tighter clearance for joiner / feet cradles
FLOOR = 2.0                  # every part supports the profile bottom 2.0 mm above the piano
T = 2.2                      # general wall

# ---- Controller board: QuinLED Dig2Go v1.05 (quinled.info/dig2go-dimensions) ----
BW, BL = 33.4, 51.3          # PCB width x length (published drawing)
B_TOTAL_H = 17.0             # PCB + components, both sides ("about 17 mm", published)
STANDOFF = 3.0               # VERIFY: bottom-side component height
HOLE_PILOT = 1.7             # M2 self-tapping pilot; VERIFY board hole size (drawing ~2.6 mm ring)
# Board drawing coords (origin = board bottom-left, +y toward LED connector).
# Mapping into cap coords: board centre at (0,0); drawing +y -> cap -X (toward rail), drawing +x -> cap +Y.
def b2c(dx, dy): return (-(dy - BL / 2), dx - BW / 2)
HOLES = [b2c(2.6, 2.6), b2c(BW - 2.6, 2.6), b2c(2.6, BL - 14.58)]
MIC = b2c(24.8, BL - 2.0)    # read off the drawing (pixel measurement) VERIFY
# USB-C centred on the drawing's bottom edge  -> cap +X wall, Y = 0
# LED connector centred on the top edge, protrudes ~1.8 mm -> cap -X side

# ---- Controller pod ----
CAV_X0, CAV_X1 = -(BL / 2) - 3.0, (BL / 2) + 0.5     # extra room for the LED connector
CAV_Y = BW + 1.0
CAV_Z = FLOOR + STANDOFF + B_TOTAL_H + 1.0            # floor..underside of lid
SIDE = 4.0                                            # thick side walls carry the lid screws
LID = 2.0
POD_X0, POD_X1 = CAV_X0 - T, CAV_X1 + T
POD_Y = CAV_Y + 2 * SIDE
SLEEVE_D = 14.0                                       # profile insertion depth
SW, SH = PW + 2 * C + 2 * T, FLOOR + PH + 2 * C + T   # sleeve outer

def box(x0, x1, y0, y1, z0, z1):
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))

def felt_recess(part, pts, d=10.0, depth=0.8):
    for (x, y) in pts:
        part = part.cut(cq.Workplane("XY").circle(d / 2).extrude(depth).translate((x, y, 0)))
    return part

def sleeve(x0, x1, closed_end=None):
    s = box(x0, x1, -SW / 2, SW / 2, 0, SH)
    s = s.cut(box(x0 - 1, x1 + 1, -(PW / 2 + C), PW / 2 + C, FLOOR, FLOOR + PH + 2 * C))
    if closed_end == "min":
        s = s.union(box(x0, x0 + T, -SW / 2, SW / 2, 0, SH))
    return s

def controller_base():
    pod = box(POD_X0, POD_X1, -POD_Y / 2, POD_Y / 2, 0, CAV_Z)
    pod = pod.cut(box(CAV_X0, CAV_X1, -CAV_Y / 2, CAV_Y / 2, FLOOR, CAV_Z + 1))
    for (x, y) in HOLES:   # standoffs
        pod = pod.union(cq.Workplane("XY").circle(2.5).extrude(STANDOFF).translate((x, y, FLOOR)))
        pod = pod.cut(cq.Workplane("XY").circle(HOLE_PILOT / 2).extrude(STANDOFF + 0.1).translate((x, y, FLOOR)))
    # USB-C opening in the +X wall (13 x 9 mm, spans either board side) VERIFY height
    zb = FLOOR + STANDOFF
    pod = pod.cut(box(CAV_X1 - 1, POD_X1 + 1, -6.5, 6.5, zb - 3.5, zb + 5.5))
    # mic port through the floor
    pod = pod.cut(cq.Workplane("XY").circle(1.5).extrude(FLOOR + 1).translate((MIC[0], MIC[1], -0.5)))
    # sleeve on the -X face, bottom-aligned, centred in Y
    pod = pod.union(sleeve(POD_X0 - SLEEVE_D, POD_X0))
    # wire pass-through from profile interior into the pod
    pod = pod.cut(box(POD_X0 - 1, CAV_X0 + 1, -5.0, 5.0, FLOOR + 1.0, FLOOR + 1.0 + 8.0))
    # lid screw pilots, vertical in the thick side walls
    for x in (POD_X0 + 6, POD_X1 - 6):
        for y in (-(POD_Y / 2 - SIDE / 2), POD_Y / 2 - SIDE / 2):
            pod = pod.cut(cq.Workplane("XY").circle(HOLE_PILOT / 2).extrude(8).translate((x, y, CAV_Z - 8)))
    pod = felt_recess(pod, [(POD_X0 + 9, -POD_Y / 2 + 9), (POD_X0 + 9, POD_Y / 2 - 9),
                            (POD_X1 - 9, -POD_Y / 2 + 9), (POD_X1 - 9, POD_Y / 2 - 9)])
    return pod

def controller_lid():
    lid = box(POD_X0, POD_X1, -POD_Y / 2, POD_Y / 2, 0, LID)
    lip = box(CAV_X0 + 0.2, CAV_X1 - 0.2, -CAV_Y / 2 + 0.2, CAV_Y / 2 - 0.2, -2.0, 0)
    lip = lip.cut(box(CAV_X0 + 1.4, CAV_X1 - 1.4, -CAV_Y / 2 + 1.4, CAV_Y / 2 - 1.4, -2.1, 0.1))
    lid = lid.union(lip)
    for x in (POD_X0 + 6, POD_X1 - 6):
        for y in (-(POD_Y / 2 - SIDE / 2), POD_Y / 2 - SIDE / 2):
            lid = lid.cut(cq.Workplane("XY").circle(1.2).extrude(LID + 1).translate((x, y, -0.5)))
            lid = lid.cut(cq.Workplane("XY").circle(2.2).extrude(1.0).translate((x, y, LID - 1.0)))
    lid = lid.cut(cq.Workplane("XY").circle(1.5).extrude(LID + 3).translate((MIC[0], MIC[1], -2.5)))  # mic port
    for i in range(5):   # vent slots over the board
        x = -12 + i * 6
        lid = lid.cut(box(x - 1.0, x + 1.0, -9, 9, -2.5, LID + 0.5))
    return lid.translate((0, 0, CAV_Z))   # shown in its fitted position

def blank_cap():
    c = sleeve(-SLEEVE_D - T, 0, closed_end="min")
    return felt_recess(c, [(-(SLEEVE_D + T) / 2, 0)], d=8.0)

def cradle(length, clearance):
    w_in = PW + 2 * clearance
    wall_h = FLOOR + 10.0          # grips the lower 10 mm of the profile; diffuser stays clear
    c = box(-length / 2, length / 2, -(w_in / 2 + T), w_in / 2 + T, 0, wall_h)
    c = c.cut(box(-length / 2 - 1, length / 2 + 1, -w_in / 2, w_in / 2, FLOOR, wall_h + 1))
    return c

def joiner():
    j = cradle(60.0, CJ)
    # wire/connector clearance pocket in the floor under the joint
    j = j.cut(box(-6, 6, -5, 5, 0.8, FLOOR + 0.1))
    return felt_recess(j, [(-20, 0), (20, 0)], d=8.0)

def foot():
    return felt_recess(cradle(25.0, CJ), [(0, 0)], d=8.0)

PARTS = {
    "DK1-01_controller-cap-base": controller_base(),
    "DK1-02_controller-cap-lid": controller_lid(),
    "DK1-03_blank-end-cap": blank_cap(),
    "DK1-04_rail-joiner": joiner(),
    "DK1-05_support-foot": foot(),
}

if __name__ == "__main__":
    from cadquery import exporters
    for name, part in PARTS.items():
        exporters.export(part, os.path.join(OUT, name + ".step"))
        exporters.export(part, os.path.join(OUT, name + ".stl"), tolerance=0.02, angularTolerance=0.1)
        exporters.export(part, os.path.join(OUT, name + ".svg"),
                         opt={"width": 600, "height": 420, "marginLeft": 60, "marginTop": 60, "projectionDir": (1, -1.2, 0.8), "showHidden": False, "showAxes": False})
        bb = part.val().BoundingBox()
        print(f"{name}: {bb.xlen:.1f} x {bb.ylen:.1f} x {bb.zlen:.1f} mm, volume {part.val().Volume()/1000:.2f} cm3")
    # assembly of the controller end: base + lid + a 40 mm stub of profile, for the overview drawing
    stub = box(POD_X0 - SLEEVE_D - 40, POD_X0, -PW / 2, PW / 2, FLOOR, FLOOR + PH)
    asm = PARTS["DK1-01_controller-cap-base"].union(PARTS["DK1-02_controller-cap-lid"]).union(stub)
    exporters.export(asm, os.path.join(OUT, "DK1-00_controller-end-assembly.svg"),
                     opt={"width": 700, "height": 460, "marginLeft": 60, "marginTop": 60, "projectionDir": (1, -1.2, 0.8), "showHidden": False, "showAxes": False})
    exporters.export(asm, os.path.join(OUT, "DK1-00_controller-end-assembly.step"))
