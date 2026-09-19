"""Render the Mojamuddin book from every studio camera.

    blender -b models/mojamuddin_book.blend --python scripts/render_mojam_book.py

Writes renders/mojamuddin_book_<camera>.png at the resolution and sample count
stored in the .blend (2000 x 1500, 512 adaptive samples, OpenImageDenoise).

Environment overrides:
    BOOK_RENDER_DIR     alternative output directory
    BOOK_CAMERAS        comma-separated camera names (default: all CAM_* objects)
    BOOK_SAMPLES        override the Cycles sample count
    BOOK_SCALE          resolution percentage (default 100)
"""
import os
import bpy

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RENDER_DIR = os.environ.get("BOOK_RENDER_DIR", os.path.join(REPO, "renders"))
SUFFIX = {"CAM_Main": "main", "CAM_Elevated": "elevated", "CAM_Front": "front",
          "CAM_Back": "back", "CAM_Spine": "spine", "CAM_Detail": "detail"}

scene = bpy.context.scene
scene.render.engine = "CYCLES"
if os.environ.get("BOOK_SAMPLES"):
    scene.cycles.samples = int(os.environ["BOOK_SAMPLES"])
scene.render.resolution_percentage = int(os.environ.get("BOOK_SCALE", "100"))

# use the GPU when one is available (preferences are not stored in the .blend)
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for dev_type in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
        try:
            prefs.compute_device_type = dev_type
            prefs.get_devices()
        except Exception:
            continue
        if any(d.type == dev_type for d in prefs.devices):
            for d in prefs.devices:
                d.use = d.type in (dev_type, "CPU")
            scene.cycles.device = "GPU"
            break
except Exception:
    pass

names = os.environ.get("BOOK_CAMERAS")
cameras = ([bpy.data.objects[n.strip()] for n in names.split(",")] if names
           else [o for o in bpy.data.objects if o.type == "CAMERA" and o.name.startswith("CAM_")])
cameras.sort(key=lambda o: list(SUFFIX).index(o.name) if o.name in SUFFIX else 99)

os.makedirs(RENDER_DIR, exist_ok=True)
for cam in cameras:
    scene.camera = cam
    scene.render.filepath = os.path.join(RENDER_DIR, "mojamuddin_book_%s.png" % SUFFIX.get(cam.name, cam.name.lower()))
    bpy.ops.render.render(write_still=True)
    print("RENDERED", scene.render.filepath, "device:", scene.cycles.device)
print("RENDER_OK")
