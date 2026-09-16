"""Export the Noor-e-Iman book to exports/noor_e_iman_book.glb.

glTF only carries image-textured Principled materials, so the procedural paper
materials on Book_Pages are baked to textures/book_pages_*.png first. The
procedural materials are put back afterwards and the .blend is NOT saved, so
the editable file keeps its procedural setup.

Run headless:
    blender -b models/noor_e_iman_book.blend --python scripts/export_glb.py
Or from the running Blender (via MCP or the Python console):
    exec(open(r"...\\scripts\\export_glb.py").read())
"""
import os
import bpy
import bmesh
from mathutils import Vector

# --------------------------------------------------------------------------- #
# Paths and bake settings
# --------------------------------------------------------------------------- #
REPO = os.path.dirname(os.path.dirname(bpy.path.abspath(bpy.data.filepath)))
TEX_DIR = os.path.join(REPO, "textures")
EXPORT = os.path.join(REPO, "exports", "noor_e_iman_book.glb")

BAKE_W, BAKE_H = 4096, 2048
PX_PER_MM = 12.5
MARGIN_PX = 16
BAKE_SAMPLES = 4

PAGES = bpy.data.objects["Book_Pages"]
EXPORT_OBJECTS = ["Book_Noor_e_Iman", "Book_Cover", "Book_Pages"]
MM = 1000.0

# --------------------------------------------------------------------------- #
# 1. UV layout for the page block: three visible strips + one patch for hidden faces
# --------------------------------------------------------------------------- #
def layout_page_uvs(obj):
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    uv_layer = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")

    dims = obj.dimensions * MM            # (210, 297, 53) mm
    hx, hy, hz = dims.x / 2, dims.y / 2, dims.z / 2
    strip_h = dims.z * PX_PER_MM
    rows = [MARGIN_PX + i * (strip_h + MARGIN_PX) for i in range(3)]

    def px_to_uv(px, py):
        return (px / BAKE_W, py / BAKE_H)

    for f in bm.faces:
        n = f.normal
        for loop in f.loops:
            p = loop.vert.co * MM
            if n.x < -0.5:                                    # fore-edge: u along Y
                px = MARGIN_PX + (p.y + hy) * PX_PER_MM
                py = rows[0] + (p.z + hz) * PX_PER_MM
            elif n.y > 0.5:                                   # head: u along X
                px = MARGIN_PX + (p.x + hx) * PX_PER_MM
                py = rows[1] + (p.z + hz) * PX_PER_MM
            elif n.y < -0.5:                                  # tail: u along X
                px = MARGIN_PX + (p.x + hx) * PX_PER_MM
                py = rows[2] + (p.z + hz) * PX_PER_MM
            else:                                             # hidden faces: small shared patch
                a = (p.x + hx) / dims.x if abs(n.z) > 0.5 else (p.z + hz) / dims.z
                b = (p.y + hy) / dims.y
                px = 2900 + a * 900
                py = 800 + b * 1100
            loop[uv_layer].uv = px_to_uv(px, py)

    bm.to_mesh(me)
    bm.free()
    me.update()


# --------------------------------------------------------------------------- #
# 2. Bake colour, roughness and normal of the procedural paper materials
# --------------------------------------------------------------------------- #
def bake_pages(obj):
    scene = bpy.context.scene
    saved = {
        "engine": scene.render.engine,
        "samples": getattr(scene.cycles, "samples", None),
        "active": bpy.context.view_layer.objects.active,
        "selected": [o for o in scene.objects if o.select_get()],
    }
    scene.render.engine = "CYCLES"
    scene.cycles.samples = BAKE_SAMPLES
    scene.render.bake.margin = 4
    scene.render.bake.use_clear = True

    for o in scene.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    images = {}
    temp_nodes = []
    passes = [
        ("color", "DIFFUSE", {"COLOR"}, True),
        ("roughness", "ROUGHNESS", None, False),
        ("normal", "NORMAL", None, False),
    ]
    try:
        for suffix, bake_type, pass_filter, srgb in passes:
            name = f"book_pages_{suffix}"
            img = bpy.data.images.get(name) or bpy.data.images.new(name, BAKE_W, BAKE_H)
            img.scale(BAKE_W, BAKE_H)
            img.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
            images[suffix] = img

            # Every material on the object needs an active image node pointing at the target.
            for slot in obj.material_slots:
                nt = slot.material.node_tree
                node = nt.nodes.new("ShaderNodeTexImage")
                node.name = "_BAKE_TARGET"
                node.image = img
                nt.nodes.active = node
                temp_nodes.append((nt, node))

            kwargs = {"type": bake_type, "margin": 4, "use_clear": True}
            if pass_filter:
                kwargs["pass_filter"] = pass_filter
            if bake_type == "NORMAL":
                kwargs["normal_space"] = "TANGENT"
            bpy.ops.object.bake(**kwargs)

            img.filepath_raw = os.path.join(TEX_DIR, name + ".png")
            img.file_format = "PNG"
            img.save()

            for nt, node in temp_nodes:
                nt.nodes.remove(node)
            temp_nodes.clear()
    finally:
        for nt, node in temp_nodes:
            nt.nodes.remove(node)
        scene.render.engine = saved["engine"]
        if saved["samples"] is not None:
            scene.cycles.samples = saved["samples"]
        for o in scene.objects:
            o.select_set(o in saved["selected"])
        bpy.context.view_layer.objects.active = saved["active"]
    return images


def make_baked_material(images):
    mat = bpy.data.materials.get("MAT_Pages_Baked") or bpy.data.materials.new("MAT_Pages_Baked")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    n, L = nt.nodes.new, nt.links.new
    out = n("ShaderNodeOutputMaterial"); out.location = (600, 0)
    bsdf = n("ShaderNodeBsdfPrincipled"); bsdf.location = (300, 0)
    L(bsdf.outputs["BSDF"], out.inputs["Surface"])

    col = n("ShaderNodeTexImage"); col.image = images["color"]; col.location = (-300, 300)
    L(col.outputs["Color"], bsdf.inputs["Base Color"])
    rough = n("ShaderNodeTexImage"); rough.image = images["roughness"]; rough.location = (-300, 0)
    L(rough.outputs["Color"], bsdf.inputs["Roughness"])
    nrm = n("ShaderNodeTexImage"); nrm.image = images["normal"]; nrm.location = (-300, -300)
    nmap = n("ShaderNodeNormalMap"); nmap.location = (0, -300)
    L(nrm.outputs["Color"], nmap.inputs["Color"])
    L(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


# --------------------------------------------------------------------------- #
# 3. Export with the baked material swapped in, then restore
# --------------------------------------------------------------------------- #
def export_glb(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    scene = bpy.context.scene
    prev_sel = [o for o in scene.objects if o.select_get()]
    prev_active = bpy.context.view_layer.objects.active
    for o in scene.objects:
        o.select_set(o.name in EXPORT_OBJECTS)
    bpy.context.view_layer.objects.active = bpy.data.objects["Book_Cover"]
    try:
        bpy.ops.export_scene.gltf(
            filepath=path,
            export_format="GLB",
            use_selection=True,
            export_apply=True,
            export_yup=True,
            export_texcoords=True,
            export_normals=True,
            export_materials="EXPORT",
            export_image_format="AUTO",
            export_cameras=False,
            export_lights=False,
        )
    finally:
        for o in scene.objects:
            o.select_set(o in prev_sel)
        bpy.context.view_layer.objects.active = prev_active


layout_page_uvs(PAGES)
baked_images = bake_pages(PAGES)
baked_mat = make_baked_material(baked_images)

original_mats = [slot.material for slot in PAGES.material_slots]
for slot in PAGES.material_slots:
    slot.material = baked_mat
try:
    export_glb(EXPORT)
finally:
    for slot, mat in zip(PAGES.material_slots, original_mats):
        slot.material = mat

result = {
    "glb": EXPORT,
    "glb_bytes": os.path.getsize(EXPORT) if os.path.exists(EXPORT) else None,
    "baked": {k: v.filepath_raw for k, v in baked_images.items()},
}
print("EXPORT_OK", result)
