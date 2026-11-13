# v6 geometry — November 11, 2026

The supplied [hull 11-11-26.step](../../hydrostatics/v6-2026-11-11/hull%2011-11-26.step) remains in the v6 hydrostatics folder as provided. Original bytes are preserved. Its STEP header names `v5 - hull` and records export time `2026-11-12T00:29:17Z` (November 11 locally); this is the supplied v6 revision.

[Inspection report](step-inspection.json): Open CASCADE imported one solid, one shell and 90 faces. Dimensions are approximately **72.000 in along CAD Y × 20.341 in along CAD X × 12.001 in along CAD Z**. The small height excess is on an internal bow detail; the exterior flotation rim is at 12 inches. Bounds are X = ±258.326 mm, Y = 0–1828.8 mm, Z = 0–304.822 mm. STEP declares metres; Open CASCADE imports millimetres.

The raw solid fails CAD validity because planar rim face 46 is invalid. All seven selected exterior faces are individually valid: bottom 41/42, chines 43/44, sides 50/53 and transom 51. Replacing the rim with a new planar cap from face 46's outer wire and sewing it to those exterior faces produces a valid, oriented flotation solid. Internal ribs, mounts and inner surfaces do not bound displaced water. The raw material volume in the inspection report is diagnostic only because the source solid is invalid; it is not flotation displacement or a shell-mass estimate.

[Preparation script](../../hydrostatics/v6-2026-11-11/prepare_geometry.py) · [Flotation geometry checks](../../hydrostatics/v6-2026-11-11/geometry/geometry-report.json)

The exact capped envelope volume is 0.200893710 m³. Its 4,152-triangle mesh is watertight with consistent winding and differs in volume by 0.00814%. Source and mesh hashes are recorded. The original STEP has not been repaired or altered.

Axes match the inherited convention: CAD X transverse, Y forward from transom, Z above aft keel; NavalToolbox uses X = CAD Y, Y = −CAD X, Z unchanged, in full-scale metres. Confirm physical origin, transverse sign, actual downflooding openings and sealed buoyancy volumes before interpreting a loaded result. The cap assumes a dry interior below the 12-inch rim; no additional tube or appendage buoyancy is included. Rim immersion invalidates this assumption.

Review the supplied [v6 component loading](../../hydrostatics/v6-2026-11-11/component-masses.csv) and the executed [notebook](../../hydrostatics/v6-2026-11-11/navaltoolbox.ipynb).
