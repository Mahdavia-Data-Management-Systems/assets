"""Build the photoreal 3D model of the hardcover Urdu book "Mu'jam ud-Din" (Mojamuddin).

Run headless:
    blender -b --python scripts/build_mojam_book.py

or from a running Blender (e.g. through the MCP bridge):
    runpy.run_path("scripts/build_mojam_book.py", run_name="__main__")

Cover source: raw/mojam.jpeg (4846 x 2838 px, RTL layout: front | spine | back).
Texture:      textures/mojamuddin_cover_full.jpeg (byte-identical copy of the source).
Geometry:     scripts/mojam_book_geometry.py (dimensions, spine arc, UV mapping).
Output:       models/mojamuddin_book.blend, renders/mojamuddin_book_*.png

Environment overrides:
    BOOK_RENDER=0       skip the preview renders
    BOOK_SAVE=0         do not save the .blend
    BOOK_BLEND_OUT      alternative .blend output path
    BOOK_RENDER_DIR     alternative render output directory
"""
import importlib
import math
import os
import sys
import bpy
from mathutils import Vector

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
import mojam_book_geometry as G  # noqa: E402
importlib.reload(G)

REPO = os.path.dirname(SCRIPTS)
TEXTURE = os.path.join(REPO, "textures", "mojamuddin_cover_full.jpeg")
BLEND_OUT = os.environ.get("BOOK_BLEND_OUT", os.path.join(REPO, "models", "mojamuddin_book.blend"))
RENDER_DIR = os.environ.get("BOOK_RENDER_DIR", os.path.join(REPO, "renders"))
MM = G.MM

# --------------------------------------------------------------------------- #
# Scene reset (works in a live session too: wipe objects and orphan data)
# --------------------------------------------------------------------------- #
scene = bpy.context.scene
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
for col in list(bpy.data.collections):
    bpy.data.collections.remove(col)
for _ in range(4):
    bpy.data.orphans_purge(do_recursive=True)
for img in list(bpy.data.images):
    if img.users == 0:
        bpy.data.images.remove(img)

scene.unit_settings.system = "METRIC"
scene.unit_settings.length_unit = "MILLIMETERS"


def new_collection(name, parent=None):
    col = bpy.data.collections.new(name)
    (parent or scene.collection).children.link(col)
    return col


book_col = new_collection("Book_Mojamuddin")
studio_col = new_collection("Studio")

# --------------------------------------------------------------------------- #
# Material helpers
# --------------------------------------------------------------------------- #
def _new_mat(name):
    mat = bpy.data.materials.get(name)
    if mat:
        bpy.data.materials.remove(mat)
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (900, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (600, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat, nt, bsdf


def make_cover_material():
    """Printed, matte-laminated case cover carrying the artwork untouched."""
    mat, nt, bsdf = _new_mat("MAT_MojamCover")
    n, L = nt.nodes.new, nt.links.new
    img = bpy.data.images.load(TEXTURE, check_existing=True)
    img.colorspace_settings.name = "sRGB"
    tex = n("ShaderNodeTexImage"); tex.location = (-200, 300)
    tex.image = img
    tex.interpolation = "Cubic"
    tex.extension = "EXTEND"
    L(tex.outputs["Color"], bsdf.inputs["Base Color"])

    coord = n("ShaderNodeTexCoord"); coord.location = (-1200, -200)

    # fine grain of the laminated paper (roughness + bump)
    grain = n("ShaderNodeTexNoise"); grain.location = (-900, -100)
    grain.inputs["Scale"].default_value = 2500.0
    grain.inputs["Detail"].default_value = 3.0
    grain.inputs["Roughness"].default_value = 0.6
    L(coord.outputs["Object"], grain.inputs["Vector"])

    # broad waviness of the board / cover paper
    wave = n("ShaderNodeTexNoise"); wave.location = (-900, -400)
    wave.inputs["Scale"].default_value = 18.0
    wave.inputs["Detail"].default_value = 2.0
    L(coord.outputs["Object"], wave.inputs["Vector"])

    rough = n("ShaderNodeMapRange"); rough.location = (-500, -100)
    rough.inputs["To Min"].default_value = 0.42
    rough.inputs["To Max"].default_value = 0.62
    L(grain.outputs["Fac"], rough.inputs["Value"])
    L(rough.outputs["Result"], bsdf.inputs["Roughness"])

    bump_fine = n("ShaderNodeBump"); bump_fine.location = (0, -300)
    bump_fine.inputs["Strength"].default_value = 0.22
    bump_fine.inputs["Distance"].default_value = 0.0004
    L(grain.outputs["Fac"], bump_fine.inputs["Height"])
    bump_broad = n("ShaderNodeBump"); bump_broad.location = (300, -300)
    bump_broad.inputs["Strength"].default_value = 0.25
    bump_broad.inputs["Distance"].default_value = 0.001
    L(wave.outputs["Fac"], bump_broad.inputs["Height"])
    L(bump_fine.outputs["Normal"], bump_broad.inputs["Normal"])
    L(bump_broad.outputs["Normal"], bsdf.inputs["Normal"])

    bsdf.inputs["Specular IOR Level"].default_value = 0.45
    bsdf.inputs["Coat Weight"].default_value = 0.08
    bsdf.inputs["Coat Roughness"].default_value = 0.4
    return mat


def make_pastedown_material():
    mat, nt, bsdf = _new_mat("MAT_Pastedown")
    bsdf.inputs["Base Color"].default_value = (0.80, 0.74, 0.62, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.85
    return mat


def make_paper_material():
    """Plain paper for the block faces hidden inside the cover."""
    mat, nt, bsdf = _new_mat("MAT_Paper")
    bsdf.inputs["Base Color"].default_value = (0.86, 0.79, 0.64, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.85
    return mat


def make_page_edge_material():
    """Procedural stacked-paper for the fore edge, head and tail.

    Everything is driven by Object coordinates (the block lies flat in local
    space with the leaves stacked along Z), so the fine leaf lines, the
    per-leaf tone and the fanned clumps vary along Z only.
    """
    mat, nt, bsdf = _new_mat("MAT_PageEdges")
    n, L = nt.nodes.new, nt.links.new
    coord = n("ShaderNodeTexCoord"); coord.location = (-1500, 0)

    # one line per leaf: period 0.108 mm  (wave period = 0.3142 / scale)
    leaf = n("ShaderNodeTexWave"); leaf.location = (-900, 400)
    leaf.wave_type, leaf.bands_direction, leaf.wave_profile = "BANDS", "Z", "SIN"
    leaf.inputs["Scale"].default_value = 0.31416 / (G.LEAF_T * MM)
    leaf.inputs["Distortion"].default_value = 1.2
    leaf.inputs["Detail"].default_value = 2.0
    leaf.inputs["Detail Scale"].default_value = 400.0
    leaf.inputs["Detail Roughness"].default_value = 0.6
    L(coord.outputs["Object"], leaf.inputs["Vector"])

    # groups of a few leaves sitting proud or recessed: irregular bands ~0.5 mm
    band = n("ShaderNodeTexWave"); band.location = (-900, 650)
    band.wave_type, band.bands_direction, band.wave_profile = "BANDS", "Z", "SIN"
    band.inputs["Scale"].default_value = 0.31416 / 0.00055
    band.inputs["Distortion"].default_value = 4.0
    band.inputs["Detail"].default_value = 3.0
    band.inputs["Detail Scale"].default_value = 6.0
    band.inputs["Detail Roughness"].default_value = 0.7
    L(coord.outputs["Object"], band.inputs["Vector"])
    band_rng = n("ShaderNodeMapRange"); band_rng.location = (-600, 650)
    band_rng.inputs["To Min"].default_value = 0.78
    band_rng.inputs["To Max"].default_value = 1.0
    L(band.outputs["Fac"], band_rng.inputs["Value"])

    # per-leaf tone: noise squeezed along Z
    map_leaf = n("ShaderNodeMapping"); map_leaf.location = (-1200, 100)
    map_leaf.inputs["Scale"].default_value = (6.0, 6.0, 2600.0)
    noise_leaf = n("ShaderNodeTexNoise"); noise_leaf.location = (-900, 100)
    noise_leaf.inputs["Scale"].default_value = 1.0
    noise_leaf.inputs["Detail"].default_value = 3.0
    noise_leaf.inputs["Roughness"].default_value = 0.65
    L(coord.outputs["Object"], map_leaf.inputs["Vector"])
    L(map_leaf.outputs["Vector"], noise_leaf.inputs["Vector"])
    tone = n("ShaderNodeMapRange"); tone.location = (-600, 100)
    tone.inputs["To Min"].default_value = 0.78
    tone.inputs["To Max"].default_value = 1.05
    L(noise_leaf.outputs["Fac"], tone.inputs["Value"])

    # clumps of leaves fanning together every few millimetres
    map_c = n("ShaderNodeMapping"); map_c.location = (-1200, -250)
    map_c.inputs["Scale"].default_value = (3.0, 2.0, 380.0)
    clump = n("ShaderNodeTexNoise"); clump.location = (-900, -250)
    clump.inputs["Scale"].default_value = 1.0
    clump.inputs["Detail"].default_value = 2.5
    L(coord.outputs["Object"], map_c.inputs["Vector"])
    L(map_c.outputs["Vector"], clump.inputs["Vector"])
    clump_rng = n("ShaderNodeMapRange"); clump_rng.location = (-600, -250)
    clump_rng.inputs["From Min"].default_value = 0.3
    clump_rng.inputs["From Max"].default_value = 0.7
    clump_rng.inputs["To Min"].default_value = 0.74
    clump_rng.inputs["To Max"].default_value = 1.0
    L(clump.outputs["Fac"], clump_rng.inputs["Value"])

    # gentle handling / ageing tint across the edges
    age = n("ShaderNodeTexNoise"); age.location = (-900, -550)
    age.inputs["Scale"].default_value = 30.0
    age.inputs["Detail"].default_value = 4.0
    L(coord.outputs["Object"], age.inputs["Vector"])
    age_col = n("ShaderNodeValToRGB"); age_col.location = (-600, -550)
    age_col.color_ramp.elements[0].color = (0.90, 0.84, 0.72, 1.0)
    age_col.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)
    L(age.outputs["Fac"], age_col.inputs["Fac"])

    # colour: line ramp * per-leaf tone * clumps * ageing
    ramp = n("ShaderNodeValToRGB"); ramp.location = (-600, 400)
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = (0.42, 0.35, 0.25, 1.0)     # groove between leaves
    ramp.color_ramp.elements[1].position = 0.70
    ramp.color_ramp.elements[1].color = (0.74, 0.67, 0.53, 1.0)     # leaf edge (warm ivory)
    L(leaf.outputs["Fac"], ramp.inputs["Fac"])

    def multiply(a, b, factor, location):
        m = n("ShaderNodeMix"); m.data_type, m.blend_type = "RGBA", "MULTIPLY"
        m.location = location; m.inputs["Factor"].default_value = factor
        L(a, m.inputs["A"]); L(b, m.inputs["B"])
        return m.outputs["Result"]

    col = multiply(ramp.outputs["Color"], tone.outputs["Result"], 1.0, (-300, 300))
    col = multiply(col, clump_rng.outputs["Result"], 1.0, (-50, 250))
    col = multiply(col, band_rng.outputs["Result"], 1.0, (200, 250))
    col = multiply(col, age_col.outputs["Color"], 0.5, (400, 200))
    L(col, bsdf.inputs["Base Color"])

    rough = n("ShaderNodeMapRange"); rough.location = (-50, -50)
    rough.inputs["To Min"].default_value = 0.92
    rough.inputs["To Max"].default_value = 0.72
    L(leaf.outputs["Fac"], rough.inputs["Value"])
    L(rough.outputs["Result"], bsdf.inputs["Roughness"])
    bsdf.inputs["Specular IOR Level"].default_value = 0.3
    bsdf.inputs["Sheen Weight"].default_value = 0.35
    bsdf.inputs["Sheen Roughness"].default_value = 0.6

    # bump: leaf grooves + recessed clumps
    clump_h = n("ShaderNodeMath"); clump_h.operation = "MULTIPLY"; clump_h.location = (-300, -400)
    clump_h.inputs[1].default_value = 2.5
    L(clump.outputs["Fac"], clump_h.inputs[0])
    height = n("ShaderNodeMath"); height.operation = "ADD"; height.location = (-50, -400)
    L(leaf.outputs["Fac"], height.inputs[0])
    L(clump_h.outputs[0], height.inputs[1])
    band_h = n("ShaderNodeMath"); band_h.operation = "MULTIPLY"; band_h.location = (-300, -650)
    band_h.inputs[1].default_value = 2.0
    L(band.outputs["Fac"], band_h.inputs[0])
    height2 = n("ShaderNodeMath"); height2.operation = "ADD"; height2.location = (150, -450)
    L(height.outputs[0], height2.inputs[0])
    L(band_h.outputs[0], height2.inputs[1])
    bump = n("ShaderNodeBump"); bump.location = (300, -350)
    bump.inputs["Strength"].default_value = 0.8
    bump.inputs["Distance"].default_value = 0.0004
    L(height2.outputs[0], bump.inputs["Height"])
    L(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def make_headband_material():
    mat, nt, bsdf = _new_mat("MAT_Headband")
    n, L = nt.nodes.new, nt.links.new
    coord = n("ShaderNodeTexCoord"); coord.location = (-900, 0)
    wave = n("ShaderNodeTexWave"); wave.location = (-600, 0)
    wave.wave_type, wave.bands_direction, wave.wave_profile = "BANDS", "Z", "SIN"
    wave.inputs["Scale"].default_value = 0.31416 / 0.0018
    L(coord.outputs["Object"], wave.inputs["Vector"])
    ramp = n("ShaderNodeValToRGB"); ramp.location = (-300, 0)
    ramp.color_ramp.elements[0].position = 0.45
    ramp.color_ramp.elements[0].color = (0.30, 0.03, 0.04, 1.0)     # maroon
    ramp.color_ramp.elements[1].position = 0.55
    ramp.color_ramp.elements[1].color = (0.85, 0.70, 0.30, 1.0)     # gold thread
    L(wave.outputs["Fac"], ramp.inputs["Fac"])
    L(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.7
    bsdf.inputs["Sheen Weight"].default_value = 0.5
    return mat


def make_studio_material():
    mat, nt, bsdf = _new_mat("MAT_Studio")
    n, L = nt.nodes.new, nt.links.new
    coord = n("ShaderNodeTexCoord"); coord.location = (-900, 0)
    noise = n("ShaderNodeTexNoise"); noise.location = (-600, 0)
    noise.inputs["Scale"].default_value = 60.0
    noise.inputs["Detail"].default_value = 6.0
    L(coord.outputs["Object"], noise.inputs["Vector"])
    col = n("ShaderNodeMapRange"); col.location = (-300, 100)
    col.inputs["To Min"].default_value = 0.30
    col.inputs["To Max"].default_value = 0.36
    L(noise.outputs["Fac"], col.inputs["Value"])
    tint = n("ShaderNodeMix"); tint.data_type = "RGBA"; tint.blend_type = "MULTIPLY"; tint.location = (0, 100)
    tint.inputs["Factor"].default_value = 1.0
    tint.inputs["B"].default_value = (1.0, 0.97, 0.93, 1.0)
    L(col.outputs["Result"], tint.inputs["A"])
    L(tint.outputs["Result"], bsdf.inputs["Base Color"])
    rough = n("ShaderNodeMapRange"); rough.location = (-300, -150)
    rough.inputs["To Min"].default_value = 0.55
    rough.inputs["To Max"].default_value = 0.7
    L(noise.outputs["Fac"], rough.inputs["Value"])
    L(rough.outputs["Result"], bsdf.inputs["Roughness"])
    bump = n("ShaderNodeBump"); bump.location = (200, -300)
    bump.inputs["Strength"].default_value = 0.1
    bump.inputs["Distance"].default_value = 0.0005
    L(noise.outputs["Fac"], bump.inputs["Height"])
    L(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


mat_cover = make_cover_material()
mat_pastedown = make_pastedown_material()
mat_paper = make_paper_material()
mat_edges = make_page_edge_material()
mat_headband = make_headband_material()
mat_studio = make_studio_material()

# --------------------------------------------------------------------------- #
# Book objects
# --------------------------------------------------------------------------- #
root = bpy.data.objects.new("Book_Mojamuddin", None)
root.empty_display_type = "PLAIN_AXES"
root.empty_display_size = 0.1
book_col.objects.link(root)

cover = bpy.data.objects.new("Book_Cover", G.cover_mesh("Book_Cover"))
cover.data.materials.append(mat_cover)
cover.data.materials.append(mat_pastedown)
cover.vertex_groups.new(name="Corners")
book_col.objects.link(cover)

# rounded fore-edge corners, then a soft bevel on every hard edge
bev_c = cover.modifiers.new("CornerRound", "BEVEL")
bev_c.limit_method = "VGROUP"
bev_c.vertex_group = "Corners"
bev_c.width = 2.5 * MM
bev_c.segments = 6
bev_c.affect = "EDGES"
bev_e = cover.modifiers.new("EdgeSoft", "BEVEL")
bev_e.limit_method = "ANGLE"
bev_e.angle_limit = math.radians(40)
bev_e.width = 0.55 * MM
bev_e.segments = 3
bev_e.harden_normals = True

# very slight warp of the boards (they are never perfectly flat)
warp_tex = bpy.data.textures.new("BoardWarp", "CLOUDS")
warp_tex.noise_scale = 0.35
warp_tex.noise_depth = 1
warp = cover.modifiers.new("BoardWarp", "DISPLACE")
warp.texture = warp_tex
warp.texture_coords = "GLOBAL"
warp.direction = "NORMAL"
warp.strength = 0.5 * MM
warp.mid_level = 0.5

pages =bpy.data.objects.new("Book_Pages", G.pages_mesh("Book_Pages"))
pages.data.materials.append(mat_paper)
pages.data.materials.append(mat_edges)
for name in ("ForeEdge", "HeadTail", "Edges"):
    pages.vertex_groups.new(name=name)
book_col.objects.link(pages)

# leaf misalignment: two anisotropic noise displacements driven by empties
def displace_empty(name, scale):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = "CUBE"
    e.empty_display_size = 1.0
    e.scale = scale
    e.hide_render = True
    book_col.objects.link(e)
    e.parent = root
    return e


def displace(obj, name, group, empty, strength, noise_scale=1.0):
    tex = bpy.data.textures.new(name, "CLOUDS")
    tex.noise_scale = noise_scale
    tex.noise_depth = 3
    tex.noise_basis = "ORIGINAL_PERLIN"
    mod = obj.modifiers.new(name, "DISPLACE")
    mod.texture = tex
    mod.texture_coords = "OBJECT"
    mod.texture_coords_object = empty
    mod.direction = "NORMAL"
    mod.vertex_group = group
    mod.strength = strength
    mod.mid_level = 0.5
    return mod


emp_fore = displace_empty("Displace_ForeEdge", (0.008, 0.08, 0.0025))
emp_ends = displace_empty("Displace_HeadTail", (0.08, 0.008, 0.0025))
displace(pages, "LeafMisalign_Fore", "ForeEdge", emp_fore, 1.2 * MM)
displace(pages, "LeafMisalign_Ends", "HeadTail", emp_ends, 1.0 * MM)

hb_head = bpy.data.objects.new("Book_Headband_Head", G.headband_mesh("Book_Headband_Head", G.YB1 + 0.6))
hb_tail = bpy.data.objects.new("Book_Headband_Tail", G.headband_mesh("Book_Headband_Tail", G.YB0 - 0.6))
for hb in (hb_head, hb_tail):
    hb.data.materials.append(mat_headband)
    book_col.objects.link(hb)

for o in (cover, pages, hb_head, hb_tail):
    o.parent = root

# Stand the book upright on its tail edge: height -> +Z, front cover -> -Y, spine -> +X.
root.rotation_euler = (math.radians(90), 0, 0)
root.location = (0, 0, G.BOARD_H / 2 * MM)
BOOK_CENTRE = Vector((0, 0, G.BOARD_H / 2 * MM))
BOOK_FRONT_Y = -G.Z_TOP * MM

# --------------------------------------------------------------------------- #
# Studio: floor + backdrop, lights, cameras, world
# --------------------------------------------------------------------------- #
def make_cyclorama():
    import bmesh
    bm = bmesh.new()
    # floor with a curved sweep up into a wall at both ends (seamless backdrop
    # for the front-facing and the back-facing cameras alike)
    w, depth_front, depth_back, height = 4.0, -3.4, 1.6, 3.0
    v = [bm.verts.new(p) for p in ((-w, depth_front, 0), (w, depth_front, 0),
                                   (w, depth_back, 0), (-w, depth_back, 0),
                                   (w, depth_back, height), (-w, depth_back, height),
                                   (-w, depth_front, height), (w, depth_front, height))]
    bm.faces.new((v[0], v[1], v[2], v[3]))
    bm.faces.new((v[3], v[2], v[4], v[5]))
    bm.faces.new((v[1], v[0], v[6], v[7]))
    corner = [e for e in bm.edges
              if all(abs(abs(x.co.y - (depth_back + depth_front) / 2) - (depth_back - depth_front) / 2) < 1e-6
                     and x.co.z == 0 for x in e.verts)]
    bmesh.ops.bevel(bm, geom=corner, offset=0.9, segments=24, profile=0.5, affect="EDGES")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    for f in bm.faces:
        f.smooth = True
    me = bpy.data.meshes.new("Studio_Cyclorama")
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new("Studio_Cyclorama", me)
    obj.data.materials.append(mat_studio)
    studio_col.objects.link(obj)
    return obj


make_cyclorama()


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_camera(name, location, target, lens=70, fstop=8.0):
    cam = bpy.data.cameras.new(name)
    cam.lens = lens
    cam.sensor_width = 36.0
    cam.dof.use_dof = True
    cam.dof.aperture_fstop = fstop
    cam.dof.focus_distance = (Vector(target) - Vector(location)).length
    obj = bpy.data.objects.new(name, cam)
    obj.location = location
    look_at(obj, target)
    studio_col.objects.link(obj)
    return obj


def add_light(name, location, energy, size, target, color=(1.0, 1.0, 1.0), shape="SQUARE", size_y=None):
    light = bpy.data.lights.new(name, "AREA")
    light.energy = energy
    light.shape = shape
    light.size = size
    if size_y:
        light.size_y = size_y
    light.color = color
    obj = bpy.data.objects.new(name, light)
    obj.location = location
    look_at(obj, target)
    studio_col.objects.link(obj)
    return obj


C = BOOK_CENTRE
front_target = Vector((0.0, BOOK_FRONT_Y, C.z))

cam_main = add_camera("CAM_Main", (0.82, -0.80, 0.50), (0.01, -0.01, C.z - 0.005), lens=70)
cam_elev = add_camera("CAM_Elevated", (0.50, -0.70, 0.95), (0.0, -0.01, C.z - 0.02), lens=65)
cam_front = add_camera("CAM_Front", (0.0, -1.55, C.z + 0.02), front_target, lens=85)
cam_back = add_camera("CAM_Back", (0.0, 1.20, C.z + 0.02), (0.0, G.Z_TOP * MM, C.z), lens=70)
cam_spine = add_camera("CAM_Spine", (1.30, -0.40, 0.30), (G.X_SPINE0 * MM, 0.0, C.z), lens=85)
cam_detail = add_camera("CAM_Detail", (0.36, -0.30, 0.42), (0.09, -0.02, 0.29), lens=100, fstop=11)

# key front-left and high, soft fill from the front-right, kicker grazing the
# rounded spine from the right-rear, rim over the head edge, weak top ambient
add_light("KEY", (-0.35, -1.10, 1.25), 95.0, 1.2, C, color=(1.0, 0.97, 0.93))
add_light("FILL", (1.10, -0.90, 0.50), 26.0, 2.0, C, color=(0.95, 0.97, 1.0))
add_light("KICK", (1.30, 0.55, 0.60), 32.0, 0.6, (G.X_SPINE0 * MM, 0.0, C.z), color=(1.0, 0.98, 0.95))
add_light("RIM", (-0.55, 0.85, 1.05), 36.0, 0.45, C, color=(1.0, 1.0, 1.0))
add_light("TOP", (0.0, -0.2, 2.2), 10.0, 2.5, C)
add_light("BACKDROP", (0.0, -1.6, 2.4), 260.0, 3.5, (0.0, 1.6, 0.9))
# wall seen by CAM_Back: kept close to that wall with a narrow spread so it does
# not spill onto the book and change the front-facing renders
_bf = add_light("BACKDROP_FRONT", (0.0, -2.5, 2.6), 220.0, 3.5, (0.0, -3.4, 0.9))
_bf.data.spread = math.radians(70)

world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
bg.inputs["Color"].default_value = (0.22, 0.22, 0.22, 1.0)
bg.inputs["Strength"].default_value = 0.8
scene.world = world

# --------------------------------------------------------------------------- #
# Render settings
# --------------------------------------------------------------------------- #
scene.render.engine = "CYCLES"
scene.cycles.samples = 512
scene.cycles.use_adaptive_sampling = True
scene.cycles.adaptive_threshold = 0.01
scene.cycles.use_denoising = True
scene.cycles.denoiser = "OPENIMAGEDENOISE"
scene.cycles.max_bounces = 8
scene.cycles.caustics_reflective = False
scene.cycles.caustics_refractive = False
scene.render.resolution_x, scene.render.resolution_y = 2000, 1500
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_depth = "16"
scene.render.film_transparent = False
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Base Contrast"
scene.view_settings.exposure = -0.6

# GPU if one is available
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for dev_type in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
        try:
            prefs.compute_device_type = dev_type
            prefs.get_devices()
            if any(d.type == dev_type for d in prefs.devices):
                for d in prefs.devices:
                    d.use = d.type in (dev_type, "CPU")
                scene.cycles.device = "GPU"
                break
        except Exception:
            continue
except Exception:
    pass

scene.camera = cam_main

if os.environ.get("BOOK_SAVE", "1") == "1":
    os.makedirs(os.path.dirname(BLEND_OUT), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT, relative_remap=True)

if os.environ.get("BOOK_RENDER", "1") == "1":
    os.makedirs(RENDER_DIR, exist_ok=True)
    for cam, suffix in ((cam_main, "main"), (cam_elev, "elevated"), (cam_front, "front"),
                        (cam_back, "back"), (cam_spine, "spine"), (cam_detail, "detail")):
        scene.camera = cam
        scene.render.filepath = os.path.join(RENDER_DIR, f"mojamuddin_book_{suffix}.png")
        bpy.ops.render.render(write_still=True)
    scene.camera = cam_main

print("BUILD_OK", BLEND_OUT, "engine:", scene.render.engine, "device:", scene.cycles.device)
