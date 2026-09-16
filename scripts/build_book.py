"""Build the 3D model of the A4 hardcover book "Noor-e-Iman" from its print cover.

Run headless:
    blender -b --python scripts/build_book.py

Cover source: raw/book cover.pdf (498 x 310 mm, RTL layout: front | spine | back).
Texture:      textures/book_cover_full.png (300 dpi raster of the PDF).
Geometry:     scripts/book_geometry.py (dimensions, hinge radius, UV mapping).
Output:       models/noor_e_iman_book.blend, renders/noor_e_iman_book_*.png

Environment overrides:
    BOOK_RENDER=0       skip the preview renders
    BOOK_BLEND_OUT      alternative .blend output path
    BOOK_RENDER_DIR     alternative render output directory
"""
import math
import os
import sys
import bpy
from mathutils import Vector

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
import book_geometry as G  # noqa: E402

STAND_UPRIGHT = False               # True: standing on its bottom edge; False: lying flat

REPO = os.path.dirname(SCRIPTS)
TEXTURE = os.path.join(REPO, "textures", "book_cover_full.png")
BLEND_OUT = os.environ.get("BOOK_BLEND_OUT", os.path.join(REPO, "models", "noor_e_iman_book.blend"))
RENDER_DIR = os.environ.get("BOOK_RENDER_DIR", os.path.join(REPO, "renders"))

# --------------------------------------------------------------------------- #
# Scene reset
# --------------------------------------------------------------------------- #
bpy.ops.wm.read_homefile(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
scene.unit_settings.length_unit = "MILLIMETERS"


def new_collection(name, parent=None):
    col = bpy.data.collections.new(name)
    (parent or scene.collection).children.link(col)
    return col


book_col = new_collection("Book_Noor_e_Iman")
studio_col = new_collection("Studio")

# --------------------------------------------------------------------------- #
# Materials
# --------------------------------------------------------------------------- #
def make_cover_material():
    mat = bpy.data.materials.new("MAT_BookCover")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(TEXTURE)
    tex.interpolation = "Cubic"
    tex.location = (-400, 300)
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.45
    return mat


def make_board_material():
    mat = bpy.data.materials.new("MAT_Endpaper")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.92, 0.90, 0.84, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.8
    return mat


def make_paper_material():
    """Plain paper for the block faces hidden inside the cover."""
    mat = bpy.data.materials.new("MAT_Pages")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.85
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    wave = nt.nodes.new("ShaderNodeTexWave")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    wave.wave_type = "BANDS"
    wave.bands_direction = "Z"
    wave.inputs["Scale"].default_value = 5000.0
    wave.inputs["Distortion"].default_value = 0.6
    ramp.color_ramp.elements[0].color = (0.80, 0.77, 0.70, 1.0)
    ramp.color_ramp.elements[1].color = (0.95, 0.93, 0.87, 1.0)
    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def make_page_edge_material():
    """Procedural stacked-paper material for the fore-edge, head and tail of the block.

    Everything is driven by Object coordinates: the leaves stack along Z, so the
    fine lines, the per-leaf tone and the fanned clumps all vary along Z only.
    """
    mat = bpy.data.materials.new("MAT_PageEdges")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    n, L = nt.nodes.new, nt.links.new
    out = n("ShaderNodeOutputMaterial"); out.location = (900, 0)
    bsdf = n("ShaderNodeBsdfPrincipled"); bsdf.location = (600, 0)
    L(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Specular IOR Level"].default_value = 0.3
    coord = n("ShaderNodeTexCoord"); coord.location = (-1400, 0)

    # Fine leaf lines, roughly one per 0.14 mm, slightly jittered.
    wave = n("ShaderNodeTexWave"); wave.location = (-900, 300)
    wave.wave_type, wave.bands_direction, wave.wave_profile = "BANDS", "Z", "SAW"
    wave.inputs["Scale"].default_value = 7000.0
    wave.inputs["Distortion"].default_value = 0.7
    wave.inputs["Detail"].default_value = 1.0
    wave.inputs["Detail Scale"].default_value = 300.0
    wave.inputs["Detail Roughness"].default_value = 0.5
    L(coord.outputs["Object"], wave.inputs["Vector"])

    # Per-leaf tone: noise stretched along Z so it changes leaf to leaf.
    map_leaf = n("ShaderNodeMapping"); map_leaf.location = (-1150, 0)
    map_leaf.inputs["Scale"].default_value = (8.0, 8.0, 3000.0)
    noise_leaf = n("ShaderNodeTexNoise"); noise_leaf.location = (-900, 0)
    noise_leaf.inputs["Scale"].default_value = 1.0
    noise_leaf.inputs["Detail"].default_value = 3.0
    noise_leaf.inputs["Roughness"].default_value = 0.6
    L(coord.outputs["Object"], map_leaf.inputs["Vector"])
    L(map_leaf.outputs["Vector"], noise_leaf.inputs["Vector"])
    tone = n("ShaderNodeMapRange"); tone.location = (-600, 0)
    tone.inputs["To Min"].default_value = 0.68
    tone.inputs["To Max"].default_value = 1.05
    L(noise_leaf.outputs["Fac"], tone.inputs["Value"])

    # Broad ageing / handling marks.
    noise_age = n("ShaderNodeTexNoise"); noise_age.location = (-900, -300)
    noise_age.inputs["Scale"].default_value = 25.0
    noise_age.inputs["Detail"].default_value = 4.0
    L(coord.outputs["Object"], noise_age.inputs["Vector"])
    age_col = n("ShaderNodeValToRGB"); age_col.location = (-600, -300)
    age_col.color_ramp.elements[0].color = (0.86, 0.78, 0.62, 1.0)
    age_col.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)
    L(noise_age.outputs["Fac"], age_col.inputs["Fac"])

    # Clumps of leaves fanning out every few millimetres.
    map_c = n("ShaderNodeMapping"); map_c.location = (-1150, -600)
    map_c.inputs["Scale"].default_value = (3.0, 3.0, 350.0)
    clump = n("ShaderNodeTexNoise"); clump.location = (-900, -600)
    clump.inputs["Scale"].default_value = 1.0
    clump.inputs["Detail"].default_value = 2.0
    L(coord.outputs["Object"], map_c.inputs["Vector"])
    L(map_c.outputs["Vector"], clump.inputs["Vector"])
    clump_rng = n("ShaderNodeMapRange"); clump_rng.location = (-600, -600)
    clump_rng.inputs["From Min"].default_value = 0.35
    clump_rng.inputs["From Max"].default_value = 0.65
    clump_rng.inputs["To Min"].default_value = 0.75
    clump_rng.inputs["To Max"].default_value = 1.0
    L(clump.outputs["Fac"], clump_rng.inputs["Value"])

    # Colour chain: line ramp * leaf tone * ageing * clumps.
    ramp = n("ShaderNodeValToRGB"); ramp.location = (-600, 300)
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.52, 0.45, 0.35, 1.0)   # groove between leaves
    ramp.color_ramp.elements[1].position = 0.70
    ramp.color_ramp.elements[1].color = (0.95, 0.91, 0.82, 1.0)   # leaf edge
    L(wave.outputs["Fac"], ramp.inputs["Fac"])

    def multiply(a, b, factor, location):
        m = n("ShaderNodeMix"); m.data_type, m.blend_type = "RGBA", "MULTIPLY"
        m.location = location; m.inputs["Factor"].default_value = factor
        L(a, m.inputs["A"]); L(b, m.inputs["B"])
        return m.outputs["Result"]

    col = multiply(ramp.outputs["Color"], tone.outputs["Result"], 1.0, (-350, 200))
    col = multiply(col, age_col.outputs["Color"], 0.6, (-100, 150))
    col = multiply(col, clump_rng.outputs["Result"], 1.0, (150, 150))
    L(col, bsdf.inputs["Base Color"])

    # Roughness: leaf edges a little glossier than the grooves.
    rough = n("ShaderNodeMapRange"); rough.location = (-100, -150)
    rough.inputs["To Min"].default_value = 0.9
    rough.inputs["To Max"].default_value = 0.65
    L(wave.outputs["Fac"], rough.inputs["Value"])
    L(rough.outputs["Result"], bsdf.inputs["Roughness"])

    # Bump: grooves between leaves plus the recessed clumps.
    clump_h = n("ShaderNodeMath"); clump_h.operation = "MULTIPLY"; clump_h.location = (-300, -500)
    clump_h.inputs[1].default_value = 2.0
    L(clump.outputs["Fac"], clump_h.inputs[0])
    height = n("ShaderNodeMath"); height.operation = "ADD"; height.location = (0, -450)
    L(wave.outputs["Fac"], height.inputs[0])
    L(clump_h.outputs[0], height.inputs[1])
    bump = n("ShaderNodeBump"); bump.location = (300, -300)
    bump.inputs["Strength"].default_value = 0.6
    bump.inputs["Distance"].default_value = 0.0005
    L(height.outputs[0], bump.inputs["Height"])
    L(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


mat_cover = make_cover_material()
mat_board = make_board_material()
mat_pages = make_paper_material()
mat_edges = make_page_edge_material()

# --------------------------------------------------------------------------- #
# Objects
# --------------------------------------------------------------------------- #
root = bpy.data.objects.new("Book_Noor_e_Iman", None)
root.empty_display_type = "PLAIN_AXES"
root.empty_display_size = 0.1
book_col.objects.link(root)

cover = bpy.data.objects.new("Book_Cover", G.cover_mesh("Book_Cover"))
cover.data.materials.append(mat_cover)
cover.data.materials.append(mat_board)
book_col.objects.link(cover)

pages = bpy.data.objects.new("Book_Pages", G.pages_mesh("Book_Pages"))
pages.data.materials.append(mat_pages)
pages.data.materials.append(mat_edges)
book_col.objects.link(pages)

for o in (cover, pages):
    o.parent = root

# The meshes are modelled lying flat (front +Z, spine +X, height +Y). The root
# empty can stand the book upright: height -> +Z, front cover -> -Y (towards the
# viewer), spine stays on +X. The bottom edge then rests on Z = 0.
if STAND_UPRIGHT:
    root.rotation_euler = (math.radians(90), 0, 0)
    root.location.z = (G.HALF_H + G.OVERHANG) * G.MM
BOOK_CENTRE = Vector((0, 0, (G.HALF_H + G.OVERHANG) * G.MM)) if STAND_UPRIGHT else Vector((0, 0, 0))

# --------------------------------------------------------------------------- #
# Studio: cameras, lights, world
# --------------------------------------------------------------------------- #
def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_camera(name, location, target=(0, 0, 0), lens=50):
    cam = bpy.data.cameras.new(name)
    cam.lens = lens
    obj = bpy.data.objects.new(name, cam)
    obj.location = location
    look_at(obj, target)
    studio_col.objects.link(obj)
    return obj


def add_light(name, kind, location, energy, size=1.0, target=(0, 0, 0)):
    light = bpy.data.lights.new(name, kind)
    light.energy = energy
    if kind == "AREA":
        light.size = size
    obj = bpy.data.objects.new(name, light)
    obj.location = location
    look_at(obj, target)
    studio_col.objects.link(obj)
    return obj


C = BOOK_CENTRE
if STAND_UPRIGHT:
    cam_front = add_camera("CAM_FrontSpine", (0.48, -0.60, 0.30), target=C, lens=55)
    cam_back = add_camera("CAM_Back", (-0.48, 0.60, 0.30), target=C, lens=55)
    cam_spine = add_camera("CAM_Spine", (0.70, -0.12, 0.18), target=(0.10, 0, C.z), lens=60)
    add_light("KEY", "AREA", (0.55, -0.65, 0.65), 45, size=0.8, target=C)
    add_light("FILL", "AREA", (-0.65, -0.45, 0.35), 18, size=1.2, target=C)
    add_light("RIM", "AREA", (0.15, 0.70, 0.55), 25, size=0.6, target=C)
    add_light("BACKFILL", "AREA", (-0.35, 0.65, 0.25), 40, size=1.0, target=C)
else:
    cam_front = add_camera("CAM_FrontSpine", (0.42, -0.42, 0.36), lens=55)
    cam_back = add_camera("CAM_Back", (-0.42, -0.42, -0.36), lens=55)
    cam_spine = add_camera("CAM_Spine", (0.55, -0.15, 0.05), target=(0.05, 0, 0), lens=60)
    add_light("KEY", "AREA", (0.5, -0.5, 0.7), 45, size=0.8)
    add_light("FILL", "AREA", (-0.6, -0.3, 0.4), 18, size=1.2)
    add_light("RIM", "AREA", (0.1, 0.7, 0.5), 25, size=0.6)
    add_light("BACKFILL", "AREA", (-0.3, -0.5, -0.7), 40, size=1.0)

world = bpy.data.worlds.new("World")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.35, 0.35, 0.35, 1.0)
scene.world = world

# --------------------------------------------------------------------------- #
# Render settings + output
# --------------------------------------------------------------------------- #
scene.render.resolution_x, scene.render.resolution_y = 1600, 1200
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False
for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
    try:
        scene.render.engine = engine
        break
    except TypeError:
        continue
if scene.render.engine == "CYCLES":
    scene.cycles.samples = 64
    scene.cycles.use_denoising = True

scene.camera = cam_front
os.makedirs(os.path.dirname(BLEND_OUT), exist_ok=True)
os.makedirs(RENDER_DIR, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT, relative_remap=True)

if os.environ.get("BOOK_RENDER", "1") == "1":
    for cam, suffix in ((cam_front, "front_spine"), (cam_back, "back"), (cam_spine, "spine")):
        scene.camera = cam
        scene.render.filepath = os.path.join(RENDER_DIR, f"noor_e_iman_book_{suffix}.png")
        bpy.ops.render.render(write_still=True)
    scene.camera = cam_front

print("BUILD_OK", BLEND_OUT, "engine:", scene.render.engine)
