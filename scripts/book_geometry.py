"""Geometry for the Noor-e-Iman book: cover shell and page block.

All dimensions are in millimetres; meshes are emitted in metres.
The book is modelled lying flat: front cover +Z, spine +X, height along +Y.

The cover is one closed C-shaped profile in the XZ plane extruded along Y.
The two hinges where the spine meets the boards are rounded with HINGE_RADIUS
(outer) and HINGE_RADIUS - BOARD_T (inner), so the wall thickness stays
constant. The page block gets matching bevels so it sits flush inside.

UVs on the outer wrap follow the unrolled surface: front panel, around the
hinge, along the spine, around the second hinge, then the back panel, so the
printed cover reads as one continuous sheet.
"""
import math
import bpy
import bmesh
from mathutils import Vector

MM = 0.001

PANEL_W, PANEL_H = 210.0, 297.0     # A4 trim size of the text block
SPINE_MM = 58.0                     # spine width implied by the cover layout
BOARD_T = 2.5                       # hardcover board thickness
OVERHANG = 3.0                      # board overhang beyond the text block ("square")
HINGE_RADIUS = 4.0                  # outer radius of the spine-to-board hinge (>= BOARD_T)
HINGE_SEGMENTS = 8                  # faces per quarter circle on the outer hinge

IMG_W, IMG_H = 498.0, 310.0         # cover artwork size in mm
CX_FRONT, CX_SPINE, CX_BACK = 115.0, 248.9, 382.9   # horizontal centre of each panel's artwork
CY = 154.9                                           # vertical centre of the artwork
BG_PATCH = (3.0, 3.0)               # a plain background spot in the artwork (mm)

HALF_W, HALF_H, HALF_S = PANEL_W / 2, PANEL_H / 2, SPINE_MM / 2
X_FORE = -(HALF_W + OVERHANG)       # fore-edge of the boards
X_SPINE = HALF_W + BOARD_T          # outer face of the spine
Y0, Y1 = -(HALF_H + OVERHANG), HALF_H + OVERHANG


def to_uv(ix, iy):
    return (ix / IMG_W, 1.0 - iy / IMG_H)


def _arc(cx, cz, r, a0, a1, n):
    """Points on an arc from angle a0 to a1 (degrees), excluding the start point."""
    return [
        (cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
         cz + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
        for i in range(1, n + 1)
    ]


def cover_profile():
    """Closed C profile as a list of (x, z, ix, kind).

    ``ix`` is the artwork x coordinate (mm) for outer vertices. ``kind`` is the
    type of the segment that starts at the vertex: "outer" (printed wrap),
    "fore" (board fore-edge) or "inner" (endpaper side).
    """
    R, T = HINGE_RADIUS, BOARD_T
    r_in = max(R - T, 0.0)
    n_in = max(HINGE_SEGMENTS // 2, 2)
    pts = []

    def add(x, z, ix, kind):
        pts.append((x, z, ix, kind))

    # Outer wrap: front panel -> top hinge -> spine -> bottom hinge -> back panel.
    add(X_FORE, HALF_S, CX_FRONT + X_FORE, "outer")
    add(X_SPINE - R, HALF_S, CX_FRONT + (X_SPINE - R), "outer")
    ix_a, ix_b = CX_FRONT + (X_SPINE - R), CX_SPINE - (HALF_S - R)
    for i, (x, z) in enumerate(_arc(X_SPINE - R, HALF_S - R, R, 90, 0, HINGE_SEGMENTS), 1):
        add(x, z, ix_a + (ix_b - ix_a) * i / HINGE_SEGMENTS, "outer")
    add(X_SPINE, -HALF_S + R, CX_SPINE + HALF_S - R, "outer")
    ix_a, ix_b = CX_SPINE + HALF_S - R, CX_BACK - (X_SPINE - R)
    for i, (x, z) in enumerate(_arc(X_SPINE - R, -HALF_S + R, R, 0, -90, HINGE_SEGMENTS), 1):
        add(x, z, ix_a + (ix_b - ix_a) * i / HINGE_SEGMENTS, "outer")
    add(X_FORE, -HALF_S, CX_BACK - X_FORE, "fore")

    # Inner side: back board -> spine -> front board (endpaper).
    add(X_FORE, -HALF_S + T, 0.0, "inner")
    if r_in > 0:
        add(X_SPINE - R, -HALF_S + T, 0.0, "inner")
        for x, z in _arc(X_SPINE - R, -HALF_S + R, r_in, -90, 0, n_in):
            add(x, z, 0.0, "inner")
        add(HALF_W, HALF_S - R, 0.0, "inner")
        for x, z in _arc(X_SPINE - R, HALF_S - R, r_in, 0, 90, n_in):
            add(x, z, 0.0, "inner")
    else:
        add(HALF_W, -HALF_S + T, 0.0, "inner")
        add(HALF_W, HALF_S - T, 0.0, "inner")
    add(X_FORE, HALF_S - T, 0.0, "fore")
    return pts


def _finish(bm, name, sharp_angle_deg=30.0):
    """Smooth shading with sharp edges where faces meet at a hard angle."""
    bm.normal_update()
    for f in bm.faces:
        f.smooth = True
    limit = math.radians(sharp_angle_deg)
    for e in bm.edges:
        if e.is_boundary or len(e.link_faces) != 2:
            continue
        e.smooth = e.calc_face_angle() < limit
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


def cover_mesh(name="Book_Cover"):
    """Cover shell. Material slot 0 = printed wrap, slot 1 = endpaper."""
    prof = cover_profile()
    n = len(prof)
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    v0 = [bm.verts.new(Vector((x, Y0, z)) * MM) for x, z, _, _ in prof]
    v1 = [bm.verts.new(Vector((x, Y1, z)) * MM) for x, z, _, _ in prof]

    for i in range(n):
        j = (i + 1) % n
        _, _, ix_i, kind = prof[i]
        ix_j = prof[j][2]
        f = bm.faces.new((v0[i], v0[j], v1[j], v1[i]))
        if kind == "outer":
            f.material_index = 0
            for loop, (ix, y) in zip(f.loops, ((ix_i, Y0), (ix_j, Y0), (ix_j, Y1), (ix_i, Y1))):
                loop[uv].uv = to_uv(ix, CY - y)
        else:
            f.material_index = 1 if kind == "inner" else 0
            for loop in f.loops:
                loop[uv].uv = to_uv(*BG_PATCH)

    for ring in (v0, v1):                      # head and tail caps of the boards
        f = bm.faces.new(ring)
        f.material_index = 0
        for loop in f.loops:
            loop[uv].uv = to_uv(*BG_PATCH)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return _finish(bm, name)


def pages_mesh(name="Book_Pages"):
    """Text block. Material slot 0 = hidden faces, slot 1 = visible paper edges."""
    z_in = HALF_S - BOARD_T
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector((PANEL_W, PANEL_H, 2 * z_in)) * MM, verts=bm.verts[:])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

    r_in = max(HINGE_RADIUS - BOARD_T, 0.0)
    if r_in > 0:
        # The two edges along Y where the block meets the rounded inner hinges.
        # Mesh coordinates are float32, so allow ~1e-3 mm slack.
        hinge_edges = [
            e for e in bm.edges
            if all(abs(v.co.x / MM - HALF_W) < 1e-3 for v in e.verts)
            and len({round(v.co.z, 5) for v in e.verts}) == 1
        ]
        bmesh.ops.bevel(bm, geom=hinge_edges, offset=r_in * MM, offset_type="OFFSET",
                        segments=max(HINGE_SEGMENTS // 2, 2), profile=0.5, affect="EDGES")

    bm.normal_update()
    for f in bm.faces:
        visible = f.normal.x < -0.5 or abs(f.normal.y) > 0.5   # fore-edge, head, tail
        f.material_index = 1 if visible else 0
    return _finish(bm, name)
