# v6 hydrostatics setup

[Notebook](navaltoolbox.ipynb) · [Loading table](component-masses.csv) · [Geometry intake](../../geometry/v6-2026-11-11/README.md)

[Completed v6 partial-loading run](results/navaltoolbox-20261112T004048182860Z/REPORT.md): **153.595 lb**, midship draft **5.19 in**, minimum rim freeboard **5.56 in** and initial transverse GM **3.74 in**. The analytical-box, loading-CG and buoyancy-balance checks passed.

Seven filled rows are included: the 25 lb shell, three 30.865 lb batteries, two 3 lb motor assemblies and 30 lb front payload. The thirteen blank-weight rows are excluded as authorized by the user; the result is a partial-loading case. Each run saves the original CSV and the included/excluded rows. The supplied v6 geometry is used; no v5 loading is substituted.

## Run

From the repository root, install the existing hydrostatics dependencies without running a historical study:

```sh
sh hull/hydrostatics/setup.sh --install-only
```

Open `navaltoolbox.ipynb` with the hydrostatics `.venv` interpreter or an existing Python kernel of the same version, then run top to bottom. Rerunning creates a fresh results folder. The notebook adds the local environment's packages to its import path, as v5 did.

## Inputs and assumptions

1. The supplied source is [hull 11-11-26.step](hull%2011-11-26.step), kept in this folder as provided. It measures 72 × 20.34 × 12 inches. Review the [inspection and buoyancy notes](../../geometry/v6-2026-11-11/README.md) and confirm the CAD frame and actual openings/sealed volumes.
2. Reviewed flotation geometry is saved in `geometry/` and ready for routine runs. [prepare_geometry.py](prepare_geometry.py) reuses v5's cap, meshing and validation workflow with v6's reviewed exterior faces 41–44, 50, 51 and 53. The raw STEP's rim face 46 is invalid; a fresh cap made from its outer wire yields a valid flotation solid. Internal ribs and mounts are excluded from the displaced-water boundary.
3. Geometry regeneration requires [requirements-geometry.txt](../requirements-geometry.txt) in a CAD interpreter. Run `python hull/hydrostatics/v6-2026-11-11/prepare_geometry.py` from the repository root with that interpreter. The source hash locks the reviewed face selection. The saved mesh has 4,152 triangles, consistent winding, watertightness and a 0.00814% difference from the exact envelope volume. The runner verifies STEP/STL hashes on every solve.
4. The loading CSV contains the supplied v6 masses and CGs. Update the component list and values for future cases. Enter pounds and CG coordinates in inches: X transverse, Y forward from transom, Z above aft keel. Confirm this frame against CAD; positions are centers of gravity. Include complete shell, finish, structure, equipment and payload without double counting.
5. Confirm water density (proposed freshwater: 998.2 kg/m³) and loading configuration. The notebook uses `ALLOW_BLANK_MASSES = True` for this user-authorized partial-loading case; omitted rows appear in the report. Set it to `False` to require every listed component to have a mass.

The study rejects invalid filled masses or CGs. Blank weights are excluded for the current case; they are not estimated.

## Level-water drawing

The notebook includes a simple side view with horizontal water and the v6 hull rotated to its calculated trim (1.81° bow up for the saved loading). It uses equal length/height scales and omits heel so the trim is clear. Each notebook run saves `level-water-side-view.png` alongside its other results and embeds the drawing in the notebook.

## Reuse and outputs

[Shared study runner](../study.py) extracts the component-loading and reporting code from the completed v5 notebook. It retains the analytical-box benchmark, all three loading-CG coordinates, the 0.1% buoyancy balance check, duplicate-row handling and fresh timestamped output folders. Historical notebooks and results remain unchanged. Plot length follows the supplied mesh; no v5 hull length is imposed.

Each successful solve writes `results/navaltoolbox-<UTC timestamp>/` containing `REPORT.md`, `hydrostatics.csv`, `study.json`, `hydrostatics.png`, the loading snapshot, and included/excluded component lists. Outputs cover draft, trim, heel, minimum rim freeboard, waterline length, wetted area and initial transverse GM. Geometry provenance and assumptions are embedded in the study JSON and report.

A dry-interior cap is valid only while its downflooding rim remains above water. Numerical checks establish consistency, not physical validation. This is a static flotation study; the active propulsion model remains [willmarley.ipynb](../../../prop_motor_battery/willmarley.ipynb).
