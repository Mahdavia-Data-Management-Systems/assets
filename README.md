# MDMS 3D Assets

Blender models, textures and renders for Mahdavia Data Management Systems (MDMS).

## Layout

| Folder      | Contents                                                             |
|-------------|----------------------------------------------------------------------|
| `raw/`      | Source design files as received (PDF, AI, PSD, ...). Never edited.   |
| `textures/` | Rasterised textures derived from `raw/` and used by the models.      |
| `models/`   | `.blend` files. Texture paths are stored relative to the model.      |
| `renders/`  | Preview renders of each model.                                       |
| `exports/`  | Interchange exports (`.glb`) generated from the models.              |
| `scripts/`  | Blender Python scripts that build, rebuild or export models.         |

## Assets

### Noor-e-Iman book (`models/noor_e_iman_book.blend`)

Hardcover A4 book (Urdu, right-to-left) built from the print cover in
`raw/book cover.pdf`. The cover PDF is 498 x 310 mm laid out as
front | spine | back, with the front on the left as is standard for RTL books.

Rebuild from scratch (also regenerates the preview renders):

```
blender -b --python scripts/build_book.py
```

Set `BOOK_RENDER=0` in the environment to skip rendering. `BOOK_BLEND_OUT` and
`BOOK_RENDER_DIR` redirect the outputs, which is handy while the repo file is
open in Blender.

Export to glTF (`exports/noor_e_iman_book.glb`):

```
blender -b models/noor_e_iman_book.blend --python scripts/export_glb.py
```

glTF cannot carry procedural shaders, so the export script first bakes the
page-block materials to `textures/book_pages_{color,roughness,normal}.png`,
swaps in an image-based material for the export, then restores the procedural
materials. It does not save the .blend.

Geometry parameters live at the top of `scripts/book_geometry.py`, which both
the build and export scripts import:

- `PANEL_W`, `PANEL_H`: trim size of the text block (210 x 297 mm, A4).
- `HINGE_RADIUS`, `HINGE_SEGMENTS`: rounding where the spine meets the front
  and back boards (4 mm outer radius, constant wall thickness). The cover is a
  single C-shaped shell and the cover art wraps continuously around the curve.
- `SPINE_MM`: spine width. The cover layout places the three panels so that
  the spine is 58 mm wide (10 mm bleed left and right, 6.5 mm top and bottom).
  A 300-page A4 block would only be about 15 to 20 mm thick, so the artwork and
  the stated page count disagree. The model follows the artwork; the spine frame
  itself is 38 mm wide, so anything below roughly 40 mm will crop it.
- `BOARD_T`, `OVERHANG`: hardcover board thickness and overhang past the block.

Scene contents:

- Collection `Book_Noor_e_Iman`: empty `Book_Noor_e_Iman` (root), `Book_Cover`
  (three boards, UV-mapped to `textures/book_cover_full.png`), `Book_Pages`.
- Collection `Studio`: cameras `CAM_FrontSpine`, `CAM_Back`, `CAM_Spine` and
  four area lights used for the renders in `renders/`.

The book lies flat with the front cover facing +Z, the spine facing +X and the
height along +Y, centred on the origin. Setting `STAND_UPRIGHT = True` in the
build script instead rotates the root empty `Book_Noor_e_Iman` so the book
stands on its bottom edge at Z = 0 with the front cover facing -Y. The GLB
export includes the root transform, so it follows whichever pose is saved.

### Mojamuddin book (`models/mojamuddin_book.blend`)

Photoreal hardcover Urdu book "Mu'jam ud-Din" built from the flattened print
cover in `raw/mojam.jpeg` (4846 x 2838 px). The artwork is laid out
front | spine | back with the front on the left, as is standard for an RTL
book, and is used untouched: `textures/mojamuddin_cover_full.jpeg` is a
byte-identical copy. The spine strip of the artwork is plain brown with no
text. The image height is taken as the full board height, which sets the pixel
scale (9.46 px/mm) and makes the unrolled cover surface span the artwork
exactly with no distortion. Only the 1 to 3 px export line on the image
border is hidden by a 4 px UV inset.

Physical model (see the constants at the top of `scripts/mojam_book_geometry.py`):

- Text block 220 x 294 mm, 500 leaves at 0.108 mm = 54 mm thick (about 1000
  pages), rounded at the back and concave at the fore edge, slightly thinner
  towards the fore edge.
- Boards 2.5 mm thick with a 3 mm square, 5 mm French groove at each joint,
  1 mm spine shell with a 5 mm round. Closed thickness about 59 mm, so the
  book is roughly 223 x 300 x 64 mm over the boards.
- The cover is one continuous shell (front board, groove, spine, groove, back
  board) so the artwork wraps around the joints without seams. Fore-edge
  corners are rounded by a vertex-group bevel, all other edges get a 0.55 mm
  bevel, and a very low-frequency displacement warps the boards by 0.5 mm.
- The page block is a single 28k-vertex mesh. Two anisotropic Displace
  modifiers (driven by the hidden empties `Displace_ForeEdge` and
  `Displace_HeadTail`) misalign clumps of leaves by up to about 0.6 mm, and
  the procedural `MAT_PageEdges` shader adds one line per leaf, 0.5 mm leaf
  groups, per-leaf tone and bump. Small striped headbands sit in the hollow
  between block and spine at head and tail.

Rebuild from scratch (also saves the .blend; add `BOOK_RENDER=0` to skip the
renders, `BOOK_SAVE=0` to skip saving):

```
blender -b --python scripts/build_mojam_book.py
```

The build script also runs inside a live Blender session (for example through
the MCP bridge) with `runpy.run_path("scripts/build_mojam_book.py", run_name="__main__")`;
it wipes the scene first.

Render every camera at full quality (2000 x 1500, Cycles, 512 adaptive
samples, OpenImageDenoise, AgX):

```
blender -b models/mojamuddin_book.blend --python scripts/render_mojam_book.py
```

Scene contents:

- Collection `Book_Mojamuddin`: empty `Book_Mojamuddin` (root, stands the
  book upright on its tail edge with the front cover facing -Y and the spine
  on +X), `Book_Cover`, `Book_Pages`, `Book_Headband_Head`,
  `Book_Headband_Tail`, and the two displacement empties.
- Collection `Studio`: cyclorama floor/backdrop, cameras `CAM_Main` (3/4,
  70 mm), `CAM_Elevated`, `CAM_Front`, `CAM_Back`, `CAM_Spine`, `CAM_Detail`
  (macro of the head/spine corner), and area lights `KEY`, `FILL`, `KICK`
  (grazes the spine), `RIM`, `TOP`, `BACKDROP`.

Preview renders: `renders/mojamuddin_book_{main,elevated,front,back,spine,detail}.png`.

Export to glTF (`exports/mojamuddin_book.glb`, about 35 MB):

```
blender -b models/mojamuddin_book.blend --python scripts/export_mojam_glb.py
```

glTF cannot carry procedural shaders, so the export script first bakes the
page-block material to `textures/mojamuddin_pages_{color,roughness,normal}.png`
(4096 x 2048, three strips for fore edge, head and tail), swaps in an
image-based material, gives the headbands a plain maroon material, applies all
modifiers and exports only the `Book_Mojamuddin` hierarchy (no studio, lights
or cameras). The procedural materials are restored afterwards and the .blend is
not saved. The root node carries the upright pose.
