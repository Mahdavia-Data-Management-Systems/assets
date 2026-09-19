"""Export the Mojamuddin book to exports/mojamuddin_book.glb.

glTF only carries image-textured Principled materials, so the procedural
paper material on Book_Pages is baked to textures/mojamuddin_pages_*.png first
and the striped headbands get a plain material for the export. The procedural
materials are put back afterwards and the .blend is NOT saved, so the editable
file keeps its procedural setup. Modifiers (bevels, board warp, leaf
displacement) are applied in the export.

Run headless:
    blender -b models/mojamuddin_book.blend --python scripts/export_mojam_glb.py
Or from the running Blender (via MCP or the Python console):
    runpy.run_path("scripts/export_mojam_glb.py", run_name="__main__")
"""
import os
import bpy
import bmesh

# --------------------------------------------------------------------------- #
# Paths and bake settings
# --------------------------------------------------------------------------- #
REPO = os.path.dirname(os.path.dirname(bpy.path.abspath(bpy.data.filepath)))
TEX_DIR = os.path.join(REPO, "textures")
EXPORT = os.path.join(REPO, "exports", "mojamuddin_book.glb")

BAKE_W, BAKE_H = 4096, 2048
PX_PER_MM = 12.0
MARGIN_PX = 16
BAKE_SAMPLES = 4

PAGES = bpy.data.objects["Book_Pages"]
HEADBANDS = [bpy.data.objects[n] for n in ("Book_Headband_Head", "Book_Headband_Tail") if n in bpy.data.objects]
EXPORT_OBJECTS = ["Book_Mojamuddin", "Book_Cover", "Book_Pages"] + [o.name for o in HEADBANDS]
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

    xs = [v.co.x for v in bm.verts]; ys = [v.co.y for v in bm.verts]; zs = [v.co.z for v in bm.verts]
    x0, x1 = min(xs) * MM, max(xs) * MM
    y0, y1 = min(ys) * MM, max(ys) * MM
    z0, z1 = min(zs) * MM, max(zs) * MM
    dz = z1 - z0
    strip_h = dz * PX_PER_MM
    rows = [MARGIN_PX + i * (strip_h + MARGIN_PX) for i in range(3)]
    assert rows[2] + strip_h + MARGIN_PX <= BAKE_H, "bake image too small for three strips"

    def px_to_uv(px, py):
        return (px / BAKE_W, py / BAKE_H)

    for f in bm.faces:
        n = f.normal
        for loop in f.loops:
            p = loop.vert.co * MM
            if n.x < -0.5:                                    # fore edge: u along Y
                px = MARGIN_PX + (p.y - y0) * PX_PER_MM
                py = rows[0] + (p.z - z0) * PX_PER_MM
            elif n.y > 0.5:                                   # head: u along X
                px = MARGIN_PX + (p.x - x0) * PX_PER_MM
                py = rows[1] + (p.z - z0) * PX_PER_MM
            elif n.y < -0.5:                                  # tail: u along X
                px = MARGIN_PX + (p.x - x0) * PX_PER_MM
                py = rows[2] + (p.z - z0) * PX_PER_MM
            else:                                             # hidden faces (top, bottom, back): shared patch
                a = (p.x - x0) / (x1 - x0) if abs(n.z) > 0.5 else (p.z - z0) / dz
                b = (p.y - y0) / (y1 - y0)
                px = 3620 + a * 440
                py = 200 + b * 1600
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
            name = f"mojamuddin_pages_{suffix}"
            img = bpy.data.images.get(name) or bpy.data.images.new(name, BAKE_W, BAKE_H)
            img.scale(BAKE_W, BAKE_H)
            img.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
            images[suffix] = img

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
    mat = bpy.data.materials.get("MAT_MojamPages_Baked") or bpy.data.materials.new("MAT_MojamPages_Baked")
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


def make_headband_export_material():
    mat = bpy.data.materials.get("MAT_Headband_Export") or bpy.data.materials.new("MAT_Headband_Export")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.36, 0.08, 0.06, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.7
    return mat


# --------------------------------------------------------------------------- #
# 3. Export with the baked materials swapped in, then restore
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
hb_mat = make_headband_export_material()

original = {o.name: [slot.material for slot in o.material_slots] for o in [PAGES] + HEADBANDS}
for slot in PAGES.material_slots:
    slot.material = baked_mat
for hb in HEADBANDS:
    for slot in hb.material_slots:
        slot.material = hb_mat
try:
    export_glb(EXPORT)
finally:
    for o in [PAGES] + HEADBANDS:
        for slot, mat in zip(o.material_slots, original[o.name]):
            slot.material = mat

result = {
    "glb": EXPORT,
    "glb_bytes": os.path.getsize(EXPORT) if os.path.exists(EXPORT) else None,
    "baked": {k: v.filepath_raw for k, v in baked_images.items()},
}
print("EXPORT_OK", result)
