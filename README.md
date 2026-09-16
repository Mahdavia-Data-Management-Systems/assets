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
