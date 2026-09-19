"""Geometry for the Mojamuddin (Mu'jam ud-Din) hardcover book.

All dimensions are in millimetres; meshes are emitted in metres.
The book is modelled lying flat: front cover +Z, spine +X, head (top) +Y.
The build script stands it upright through the root empty.

Cover artwork: raw/mojam.jpeg, 4846 x 2838 px, laid out FRONT | SPINE | BACK
(front on the left, as is standard for an RTL Urdu book). The artwork height
is taken as the full board height, which gives the pixel scale; the unrolled
outer surface of the cover (front board, groove, rounded spine, groove, back
board) then spans the full artwork width with no distortion.

The cover is one closed shell profile in the XZ plane extruded along Y:
flat boards 2.5 mm thick, a shallow French groove at each joint and a gently
rounded spine 1 mm thick. The page block is rounded at the back and concave
at the fore edge, as a rounded-and-backed text block is.
"""
import math
import bpy
import bmesh
from mathutils import Vector

MM = 0.001

# --- artwork -------------------------------------------------------------- #
PX_W, PX_H = 4846.0, 2838.0
UV_INSET_PX = 4.0                    # hide the 1-3 px export line on the image border

# --- book ----------------------------------------------------------------- #
BOARD_H = 300.0                      # artwork height = board height
SCALE = PX_H / BOARD_H               # px per mm (9.46)
UNROLL = PX_W / SCALE                # unrolled outer cover length (512.3 mm)
OVERHANG = 3.0                       # board "square" past the block
BOARD_T = 2.5
SPINE_T = 1.0                        # cover shell thickness at groove and spine
GROOVE = 5.0                         # French groove width
GROOVE_DEPTH = 1.8
LEAVES = 500                         # ~1000 pages
LEAF_T = 0.108
BLOCK_T = LEAVES * LEAF_T            # 54.0
BLOCK_H = BOARD_H - 2 * OVERHANG     # 294
BLOCK_BACK_SAG = 5.0                 # rounding of the block back
BLOCK_FORE_SAG = 4.0                 # matching concave fore edge
BLOCK_TAPER = 0.5                    # block slightly thinner at the fore edge
SPINE_SAG = 5.0                      # bulge of the spine over its chord
Z_TOP = BLOCK_T / 2 + BOARD_T        # 29.5 outer face of the boards
Z_SPINE = Z_TOP - 0.5                # spine chord half-height

# spine arc: chord 2*Z_SPINE, sagitta SPINE_SAG
R_SPINE = (Z_SPINE ** 2 + SPINE_SAG ** 2) / (2 * SPINE_SAG)
PHI_SPINE = math.asin(Z_SPINE / R_SPINE)
SPINE_ARC = 2 * R_SPINE * PHI_SPINE  # 58.6 mm printed spine

PANEL = (UNROLL - SPINE_ARC) / 2     # printed width of board + groove
BOARD_W = PANEL - GROOVE
BLOCK_W = BOARD_W - OVERHANG
X_FORE = -(BLOCK_W / 2 + OVERHANG)   # fore edge of the boards
X_BOARD = X_FORE + BOARD_W           # spine-side edge of the boards (= block back start)
X_SPINE0 = X_BOARD + GROOVE          # start of the spine arc
XC_SPINE = X_SPINE0 - R_SPINE * math.cos(PHI_SPINE)
Y0, Y1 = -BOARD_H / 2, BOARD_H / 2   # tail, head of the boards
YB0, YB1 = -BLOCK_H / 2, BLOCK_H / 2 # tail, head of the block

N_BOARD_X = 22                       # board profile subdivisions along X
N_GROOVE = 6
N_SPINE = 24
N_Y = 40                             # extrusion slices along Y


def to_uv(px, py):
    """Artwork pixel (x from left, y from bottom) -> UV."""
    return (px / PX_W, py / PX_H)


def u_of_s(s):
    """Unrolled arc length (mm from the front fore edge) -> artwork x pixel."""
    return UV_INSET_PX + s * (PX_W - 2 * UV_INSET_PX) / UNROLL


def v_of_y(y):
    return UV_INSET_PX + (y - Y0) * (PX_H - 2 * UV_INSET_PX) / BOARD_H


# --------------------------------------------------------------------------- #
# Cover shell
# --------------------------------------------------------------------------- #
def _outer_half():
    """Outer profile from the front fore-edge corner to the spine centre: (x, z, thickness)."""
    pts = []
    for i in range(N_BOARD_X + 1):
        t = i / N_BOARD_X
        pts.append((X_FORE + t * BOARD_W, Z_TOP, BOARD_T))
    for i in range(1, N_GROOVE + 1):
        t = i / N_GROOVE
        x = X_BOARD + t * GROOVE
        z = Z_TOP + (Z_SPINE - Z_TOP) * t - GROOVE_DEPTH * math.sin(math.pi * t)
        pts.append((x, z, SPINE_T))
    half_n = N_SPINE // 2
    for i in range(1, half_n + 1):
        a = PHI_SPINE * (1 - i / half_n)
        pts.append((XC_SPINE + R_SPINE * math.cos(a), R_SPINE * math.sin(a), SPINE_T))
    return pts


def cover_profile():
    """Closed ring of (x, z, s, kind) for the outer surface followed by the inner surface.

    kind is the type of the segment starting at that vertex:
    'outer' printed wrap, 'fore' printed board fore edge, 'inner' pastedown.
    s is the unrolled arc length (mm) for outer vertices; -1 for inner ones.
    """
    half = _outer_half()
    outer = half + [(x, -z, t) for x, z, t in reversed(half[:-1])]
    s = [0.0]
    for (x0, z0, _), (x1, z1, _) in zip(outer, outer[1:]):
        s.append(s[-1] + math.hypot(x1 - x0, z1 - z0))
    k = UNROLL / s[-1]                 # normalise so the wrap spans the artwork exactly
    s = [v * k for v in s]

    inner = []
    n = len(outer)
    for i, (x, z, t) in enumerate(outer):
        x0, z0, _ = outer[max(i - 1, 0)]
        x1, z1, _ = outer[min(i + 1, n - 1)]
        dx, dz = x1 - x0, z1 - z0
        L = math.hypot(dx, dz)
        nx, nz = dz / L, -dx / L       # right-hand normal: inward for this traversal
        inner.append((x + nx * t, z + nz * t))

    ring = [(x, z, si, "outer") for (x, z, _), si in zip(outer, s)]
    ring[-1] = (ring[-1][0], ring[-1][1], ring[-1][2], "fore")     # back board fore edge
    for x, z in reversed(inner):
        ring.append((x, z, -1.0, "inner"))
    ring[-1] = (ring[-1][0], ring[-1][1], -1.0, "fore")            # front board fore edge
    return ring


def _finish(bm, name, sharp_angle_deg=40.0):
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
    """Cover shell. Material slot 0 = printed wrap, slot 1 = pastedown.

    Vertex group 0 ('Corners') marks the fore-edge corner columns for a
    corner-rounding bevel modifier.
    """
    prof = cover_profile()
    n = len(prof)
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    dl = bm.verts.layers.deform.new()
    ys = [Y0 + (Y1 - Y0) * i / N_Y for i in range(N_Y + 1)]
    rings = [[bm.verts.new(Vector((x, y, z)) * MM) for x, z, _, _ in prof] for y in ys]

    for j in range(N_Y):
        ya, yb = ys[j], ys[j + 1]
        for i in range(n):
            k = (i + 1) % n
            x_i, z_i, s_i, kind = prof[i]
            s_k = prof[k][2]
            f = bm.faces.new((rings[j][i], rings[j][k], rings[j + 1][k], rings[j + 1][i]))
            if kind == "outer":
                f.material_index = 0
                for loop, (s, y) in zip(f.loops, ((s_i, ya), (s_k, ya), (s_k, yb), (s_i, yb))):
                    loop[uv].uv = to_uv(u_of_s(s), v_of_y(y))
            elif kind == "fore":
                f.material_index = 0
                # the wrap turns over the fore edge: sample the artwork's edge column
                px = PX_W - UV_INSET_PX - 0.5 if s_i > 0 else UV_INSET_PX + 0.5
                for loop, y in zip(f.loops, (ya, ya, yb, yb)):
                    loop[uv].uv = to_uv(px, v_of_y(y))
            else:
                f.material_index = 1
                for loop in f.loops:
                    loop[uv].uv = (0.5, 0.5)

    # head and tail caps (board/spine thickness): brown turn-in from the artwork edge rows
    for ring, py in ((rings[0], UV_INSET_PX + 0.5), (rings[-1], PX_H - UV_INSET_PX - 0.5)):
        f = bm.faces.new(ring)
        f.material_index = 0
        for loop in f.loops:
            x = loop.vert.co.x / MM
            s = (x - X_FORE) if loop.vert.co.z > 0 else UNROLL - (x - X_FORE)
            loop[uv].uv = to_uv(u_of_s(min(max(s, 0.0), UNROLL)), py)

    for ring in (rings[0], rings[-1]):
        for v in ring:
            if abs(v.co.x / MM - X_FORE) < 1e-3:
                v[dl][0] = 1.0

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return _finish(bm, name)


# --------------------------------------------------------------------------- #
# Page block
# --------------------------------------------------------------------------- #
R_BACK = ((BLOCK_T / 2) ** 2 + BLOCK_BACK_SAG ** 2) / (2 * BLOCK_BACK_SAG)
R_FORE = ((BLOCK_T / 2) ** 2 + BLOCK_FORE_SAG ** 2) / (2 * BLOCK_FORE_SAG)
XB_FORE = X_FORE + OVERHANG          # fore-most point of the block (top/bottom leaves)


def block_x_back(z):
    zc = min(abs(z), BLOCK_T / 2)
    return X_BOARD + BLOCK_BACK_SAG - (R_BACK - math.sqrt(max(R_BACK ** 2 - zc ** 2, 0.0)))


def block_x_fore(z):
    zc = min(abs(z), BLOCK_T / 2)
    return XB_FORE + (BLOCK_FORE_SAG - (R_FORE - math.sqrt(max(R_FORE ** 2 - zc ** 2, 0.0))))


def pages_mesh(name="Book_Pages", n_u=44, n_v=108, n_y=60):
    """Text block as one watertight quad mesh.

    Material slot 0 = faces hidden against the boards/spine, slot 1 = visible
    paper edges (fore edge, head, tail). Vertex groups: 0 'ForeEdge',
    1 'HeadTail' (displacement masks) and 2 'Edges' (all visible paper).
    """
    bm = bmesh.new()
    dl = bm.verts.layers.deform.new()
    half = BLOCK_T / 2

    def zt(u):  # top face height; slight taper towards the fore edge
        return half - BLOCK_TAPER * (1.0 - u)

    def point(u, v):
        z = -half + BLOCK_T * v
        zz = z * (zt(u) / half)
        xf, xb = block_x_fore(zz), block_x_back(zz)
        return (xf + (xb - xf) * u, zz)

    ring_uv = []
    for i in range(n_u):              # bottom edge, fore -> back
        ring_uv.append((i / n_u, 0.0))
    for j in range(n_v):              # back arc, bottom -> top
        ring_uv.append((1.0, j / n_v))
    for i in range(n_u):              # top edge, back -> fore
        ring_uv.append((1.0 - i / n_u, 1.0))
    for j in range(n_v):              # fore arc, top -> bottom
        ring_uv.append((0.0, 1.0 - j / n_v))
    nr = len(ring_uv)

    ys = [YB0 + (YB1 - YB0) * k / n_y for k in range(n_y + 1)]
    rings = []
    for y in ys:
        ring = []
        for (u, v) in ring_uv:
            x, z = point(u, v)
            ring.append(bm.verts.new(Vector((x, y, z)) * MM))
        rings.append(ring)

    side_faces = []
    for k in range(n_y):
        for i in range(nr):
            j = (i + 1) % nr
            f = bm.faces.new((rings[k][i], rings[k][j], rings[k + 1][j], rings[k + 1][i]))
            u, v = ring_uv[i]
            u2, v2 = ring_uv[j]
            if v == 0.0 and v2 == 0.0:
                kind = "bottom"
            elif u == 1.0 and u2 == 1.0:
                kind = "back"
            elif v == 1.0 and v2 == 1.0:
                kind = "top"
            else:
                kind = "fore"
            side_faces.append((f, kind))

    def cap(y, ring, flip):
        grid = {}
        for i in range(1, n_u):
            for j in range(1, n_v):
                x, z = point(i / n_u, j / n_v)
                grid[(i, j)] = bm.verts.new(Vector((x, y, z)) * MM)

        def vert(i, j):
            if (i, j) in grid:
                return grid[(i, j)]
            if j == 0:
                idx = i
            elif i == n_u:
                idx = n_u + j
            elif j == n_v:
                idx = 2 * n_u + n_v - i
            else:  # i == 0
                idx = 2 * n_u + 2 * n_v - j
            return ring[idx % nr]

        faces = []
        for i in range(n_u):
            for j in range(n_v):
                quad = (vert(i, j), vert(i + 1, j), vert(i + 1, j + 1), vert(i, j + 1))
                if flip:
                    quad = quad[::-1]
                faces.append(bm.faces.new(quad))
        return faces

    tail_faces = cap(ys[0], rings[0], flip=False)
    head_faces = cap(ys[-1], rings[-1], flip=True)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

    for f, kind in side_faces:
        f.material_index = 1 if kind == "fore" else 0
    for f in tail_faces + head_faces:
        f.material_index = 1

    for v in bm.verts:
        x = v.co.x / MM
        y = v.co.y / MM
        z = v.co.z / MM
        on_fore = x < block_x_fore(z) + 0.6
        on_ends = abs(abs(y) - BLOCK_H / 2) < 1e-3
        on_back = x > block_x_back(z) - 0.6
        on_faces = abs(abs(z) - zt((x - XB_FORE) / BLOCK_W)) < 0.35
        if on_fore and not on_faces:
            v[dl][0] = 1.0
        if on_ends and not on_back and not on_faces:
            t = (x - XB_FORE) / BLOCK_W
            v[dl][1] = max(0.0, min(1.0, 1.25 - 1.1 * t))   # tight at the spine
        if (on_fore or on_ends) and not on_back and not on_faces:
            v[dl][2] = 1.0

    return _finish(bm, name, sharp_angle_deg=40.0)


# --------------------------------------------------------------------------- #
# Headbands
# --------------------------------------------------------------------------- #
def headband_mesh(name, y, radius=1.1, n_arc=20, n_ring=8):
    """Small tube along the block back at the head or tail (y in mm)."""
    bm = bmesh.new()
    half = BLOCK_T / 2 - 1.2
    rings = []
    for i in range(n_arc + 1):
        z = -half + 2 * half * i / n_arc
        x = block_x_back(z) - 0.2
        tx, tz = block_x_back(z + 0.01) - block_x_back(z), 0.01
        L = math.hypot(tx, tz)
        tx, tz = tx / L, tz / L
        nx, nz = tz, -tx
        ring = []
        for k in range(n_ring):
            a = 2 * math.pi * k / n_ring
            c, s = math.cos(a), math.sin(a)
            ring.append(bm.verts.new(Vector((x + nx * radius * c, y + radius * s, z + nz * radius * c)) * MM))
        rings.append(ring)
    for i in range(n_arc):
        for k in range(n_ring):
            k2 = (k + 1) % n_ring
            bm.faces.new((rings[i][k], rings[i][k2], rings[i + 1][k2], rings[i + 1][k]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return _finish(bm, name, sharp_angle_deg=80.0)
