"""Reusable component-loading study extracted from the completed v5 notebook.

Keeps its box, buoyancy and loading-CG checks and timestamped run artifacts.
Historical notebooks and their saved results remain unchanged.
"""
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

IN_TO_M = .0254
KG_PER_LB = .45359237
ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'prop_motor_battery').is_dir())

def run_study(study_dir, *, density_kg_m3=998.2, allow_blank_masses=False):
    """Run the v5 component-loading workflow on a reviewed revision's geometry.

    Required geometry files: hull-envelope.stl, deck-edge.json, geometry-report.json.
    Reports must retain source/source_sha256/stl_sha256, watertight,
    winding_consistent, relative_volume_error and assumption from preparation.
    CAD loading coordinates are inches; geometry is full-scale Naval metres.
    """
    import numpy as np
    import pandas as pd
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import navaltoolbox as nt
    from IPython.display import display

    study_dir = Path(study_dir).resolve()
    study_label = study_dir.name.split('-')[0]
    if not math.isfinite(density_kg_m3) or density_kg_m3 <= 0:
        raise ValueError('Water density must be finite and positive.')
    required = [study_dir / 'component-masses.csv', *(
        study_dir / 'geometry' / name for name in
        ('hull-envelope.stl', 'deck-edge.json', 'geometry-report.json'))]
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        raise FileNotFoundError('Study inputs are not ready. See the revision README. Missing: ' + ', '.join(missing))
    review = json.loads((study_dir / 'geometry/geometry-report.json').read_text())
    if not review['watertight'] or not review['winding_consistent']:
        raise ValueError('Geometry must be watertight with consistent winding.')
    if not math.isfinite(review['relative_volume_error']) or not 0 <= review['relative_volume_error'] < .001:
        raise ValueError('Mesh/STEP volume error must be below 0.1%.')

    MASS_FILE = study_dir / 'component-masses.csv'
    input_digest = hashlib.sha256(MASS_FILE.read_bytes()).hexdigest()
    with MASS_FILE.open(newline='') as stream:
        raw_rows = list(csv.DictReader(stream))
    included, unresolved = [], []
    seen_ids = {}
    for line, raw in enumerate(raw_rows, 2):
        row = {k: (v or '').strip() for k, v in raw.items()}
        if not row['mass_lbs']:
            if any(row[k] for k in ['cg_x_in', 'cg_y_in', 'cg_z_in']):
                raise ValueError(f'Line {line}: CG provided without mass.')
            unresolved.append(dict(csv_line=line, **row))
            continue
        values = [float(row[k]) for k in ['mass_lbs', 'cg_x_in', 'cg_y_in', 'cg_z_in']]
        if not all(math.isfinite(x) for x in values) or values[0] <= 0:
            raise ValueError(f'Line {line}: mass must be positive; mass and CG must be finite.')
        identity = row['component_id']
        seen_ids[identity] = seen_ids.get(identity, 0) + 1
        included.append(dict(csv_line=line, component_id=identity,
                             label=f'{row["component"]} (CSV line {line})',
                             mass_lbs=values[0], cg_x_in=values[1], cg_y_in=values[2], cg_z_in=values[3],
                             source=row['source'], notes=row['notes']))
    if not included:
        raise ValueError('No masses have been supplied.')
    duplicate_ids = [k for k, n in seen_ids.items() if n > 1]
    loading = pd.DataFrame(included)
    total_lb = float(loading.mass_lbs.sum())
    total_kg = total_lb * KG_PER_LB
    cg_cad_in = np.average(loading[['cg_x_in', 'cg_y_in', 'cg_z_in']], axis=0, weights=loading.mass_lbs)
    # Proper rotation; retain the actual transverse offset rather than forcing zero.
    cg_naval_m = np.array([cg_cad_in[1], -cg_cad_in[0], cg_cad_in[2]]) * IN_TO_M
    print(f'Total supplied mass: {total_lb:.3f} lb / {total_kg:.3f} kg')
    print('Whole-boat CAD CG (X transverse, Y forward, Z up), inches:', cg_cad_in.round(5))
    display(loading)
    if duplicate_ids:
        print('Repeated component IDs retained as separate physical rows:', duplicate_ids)
    if unresolved:
        print(f'PARTIAL LOADING: {len(unresolved)} blank rows excluded:')
        display(pd.DataFrame(unresolved)[['csv_line', 'component_id', 'component']])
        if not allow_blank_masses:
            raise ValueError('Fill all masses or explicitly set allow_blank_masses=True for a partial-loading study.')

    geometry_dir = study_dir / 'geometry'
    geometry = json.loads((geometry_dir / 'geometry-report.json').read_text())
    mesh_file = geometry_dir / 'hull-envelope.stl'
    assert hashlib.sha256(mesh_file.read_bytes()).hexdigest() == geometry['stl_sha256']
    assert hashlib.sha256((ROOT / geometry['source']).read_bytes()).hexdigest() == geometry['source_sha256']
    assert hashlib.sha256(MASS_FILE.read_bytes()).hexdigest() == input_digest, 'Loading changed: rerun input cell.'

    def box_benchmark():
        length, beam, height, draft = 1.8288, .6096, .3048, .12
        box = nt.Vessel(nt.Hull.from_box(length, beam, height))
        xmin, xmax, ymin, ymax, zmin, zmax = box.get_bounds()
        mass = length * beam * draft * density_kg_m3
        load = nt.LoadingCondition('Analytical box')
        load.add_mass_simple('Centered box mass', mass,
                             ((xmin+xmax)/2, (ymin+ymax)/2, zmin+draft/2), nt.MassCategory.lightship())
        s = nt.HydrostaticsCalculator(box, water_density=density_kg_m3).from_loading(load)
        expected = dict(volume=length*beam*draft, waterplane_area=length*beam,
                        wetted_surface_area=length*beam+2*(length+beam)*draft)
        errors = {name: abs(float(getattr(s, name))/exact-1) for name, exact in expected.items()}
        assert max(errors.values()) < .005, errors
        assert abs(s.trim) < .05 and abs(s.heel) < .05
        return errors

    benchmark = box_benchmark()
    vessel = nt.Vessel(nt.Hull(str(mesh_file)))
    rim = [tuple(point) for point in json.loads((geometry_dir / 'deck-edge.json').read_text())]
    vessel.add_deck_edge(nt.DeckEdge.from_points(f'Complete {study_label} rim', rim, nt.DeckEdgeSide.port()))
    condition = nt.LoadingCondition(f'{study_label} supplied-row loading' if unresolved else f'{study_label} complete loading')
    for row in included:
        cog = (row['cg_y_in']*IN_TO_M, -row['cg_x_in']*IN_TO_M, row['cg_z_in']*IN_TO_M)
        condition.add_mass_simple(row['label'], row['mass_lbs']*KG_PER_LB, cog, nt.MassCategory.lightship())
    calculator = nt.HydrostaticsCalculator(vessel, water_density=density_kg_m3)
    state = calculator.from_loading(condition)
    balance_error = abs(float(state.volume)*density_kg_m3/total_kg-1)
    assert math.isfinite(balance_error) and balance_error < .001, 'Buoyancy balance failed.'
    assert state.freeboard is not None
    result = dict(mass_lb=total_lb, mass_kg=total_kg,
                  draft_aft_in=float(state.draft_ap)/IN_TO_M,
                  draft_midship_in=float(state.draft)/IN_TO_M,
                  draft_forward_in=float(state.draft_fp)/IN_TO_M,
                  trim_bow_down_deg=float(state.trim), heel_deg=float(state.heel),
                  freeboard_min_in=float(state.freeboard)/IN_TO_M,
                  waterline_length_in=float(state.lwl)/IN_TO_M,
                  submerged_length_in=float(state.los)/IN_TO_M,
                  wetted_area_in2=float(state.wetted_surface_area)/IN_TO_M**2,
                  waterplane_area_in2=float(state.waterplane_area)/IN_TO_M**2,
                  displacement_volume_l=float(state.volume)*1000,
                  gm_transverse_in=None if state.gmt is None else float(state.gmt)/IN_TO_M,
                  mass_balance_relative_error=balance_error,
                  dry_hull_assumption_ok=bool(state.freeboard > 0))
    assert all(v is None or math.isfinite(v) for v in result.values())
    # Check that the native component loading actually preserved the supplied CG.
    native_cg = np.array([state.lcg, state.tcg, state.vcg], dtype=float)
    assert np.allclose(native_cg, cg_naval_m, atol=1e-7), (native_cg, cg_naval_m)
    display(pd.DataFrame([result]).T.rename(columns={0:'Baseline'}))
    print('Analytical box maximum relative error:', max(benchmark.values()))
    print(f'Mass balance error: {balance_error:.5%}')
    if not result['dry_hull_assumption_ok']:
        print('RIM IMMERSED: dry-interior flotation assumption is invalid.')
    if result['gm_transverse_in'] is not None and result['gm_transverse_in'] <= 0:
        print('NONPOSITIVE TRANSVERSE GM: this equilibrium is not initially stable in roll.')

    # Save an immutable run folder; rerunning never overwrites earlier results.
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = study_dir / 'results' / f'navaltoolbox-{stamp}'
    output.mkdir(parents=True, exist_ok=False)
    pd.DataFrame([result]).to_csv(output / 'hydrostatics.csv', index=False)
    pd.DataFrame(included).to_csv(output / 'included-components.csv', index=False)
    pd.DataFrame(unresolved).to_csv(output / 'excluded-blank-components.csv', index=False)
    (output / 'component-masses-input.csv').write_bytes(MASS_FILE.read_bytes())
    assumptions = [
        f'Water density {density_kg_m3:g} kg/m³.',
        'Loading CSV: X transverse; Y forward from transom; Z above aft keel. Naval X = CAD Y; naval Y = -CAD X; Z unchanged. Confirm against the reviewed geometry.',
        geometry['assumption'],
        'Every filled CSV row is included independently; repeated component IDs are separate rows.',
        'Blank component rows excluded by explicit partial-loading opt-in.' if unresolved else 'All component rows have masses.',
        'Static equilibrium and initial GM only; no speed, planing, waves or large-angle stability calculation.'
    ]
    metadata = dict(created_utc=datetime.now(timezone.utc).isoformat(),
                    navaltoolbox_version=version('navaltoolbox'),
                    input_file=str(MASS_FILE.relative_to(ROOT) if MASS_FILE.is_relative_to(ROOT) else MASS_FILE), input_sha256=input_digest,
                    density_kg_m3=density_kg_m3, cg_cad_in=cg_cad_in.tolist(), cg_naval_m=cg_naval_m.tolist(),
                    loading_scope="Filled component rows; blank masses excluded only by explicit opt-in", included_components=included, excluded_blank_components=unresolved,
                    duplicate_ids=duplicate_ids, assumptions=assumptions, geometry=geometry,
                    analytical_box_relative_errors=benchmark, result=result)
    (output / 'study.json').write_text(json.dumps(metadata, indent=2, allow_nan=False)+'\n')

    # Longitudinal section: hull silhouette, centerline waterline, component CGs.
    from matplotlib.collections import PolyCollection
    import struct
    data = mesh_file.read_bytes()
    count = struct.unpack_from('<I', data, 80)[0]
    triangles = np.array([struct.unpack_from('<12fH',data,84+50*i)[3:12] for i in range(count)]).reshape(-1,3,3)
    fig, axes = plt.subplots(2,1,figsize=(11,8),gridspec_kw={'height_ratios':[2,1]},layout='constrained')
    ax = axes[0]
    ax.add_collection(PolyCollection(triangles[:,:,[0,2]]/IN_TO_M,facecolors='#dce5ed',edgecolors='none',alpha=.8))
    ax.plot([vessel.get_bounds()[0]/IN_TO_M,vessel.get_bounds()[1]/IN_TO_M],[result['draft_aft_in'],result['draft_forward_in']],color='#147dbc',lw=2,label='Centerline waterline')
    sizes = loading.mass_lbs.to_numpy()*3
    ax.scatter(loading.cg_y_in,loading.cg_z_in,s=sizes,facecolors='#db9b32',edgecolors='white',label='Component CG (area ∝ mass)',zorder=4)
    ax.scatter(cg_cad_in[1],cg_cad_in[2],marker='X',s=140,color='#9b2525',label='Whole-boat CG',zorder=5)
    ax.set(xlim=(vessel.get_bounds()[0]/IN_TO_M-2,vessel.get_bounds()[1]/IN_TO_M+2),ylim=(-1,max(16,float(loading.cg_z_in.max())+2)),xlabel='Forward from transom (in)',ylabel='Above aft keel (in)')
    ax.set_aspect('equal',adjustable='box')
    ax.grid(alpha=.2)
    ax.legend(loc='upper right',fontsize=8)
    labels=['Aft draft','Midship draft','Forward draft','Min freeboard','Transverse GM']
    values=[result[k] for k in ['draft_aft_in','draft_midship_in','draft_forward_in','freeboard_min_in','gm_transverse_in']]
    axes[1].bar(labels,[v if v is not None else np.nan for v in values],color=['#147dbc']*3+['#4d9178','#db9b32'])
    for i,value in enumerate(values):
        if value is not None:
            axes[1].annotate(f'{value:.2f} in',(i,value),xytext=(0,5),textcoords='offset points',ha='center')
    axes[1].set_ylabel('Inches')
    axes[1].margins(y=.25)
    axes[1].grid(axis='y',alpha=.2)
    fig.suptitle(f'{study_label} — {total_lb:.3f} lb — '+('supplied rows only' if unresolved else 'supplied loading'))
    fig.savefig(output/'hydrostatics.png',dpi=160)
    from IPython.display import Image
    display(Image(filename=str(output / "hydrostatics.png")))
    plt.close(fig)
    summary = '\n'.join(f'- {label}: {result[key]:.3f} {unit}' for label,key,unit in [
        ('Total mass','mass_lb','lb'),('Aft draft','draft_aft_in','in'),('Midship draft','draft_midship_in','in'),
        ('Forward draft','draft_forward_in','in'),('Trim (positive bow down)','trim_bow_down_deg','deg'),
        ('Heel','heel_deg','deg'),('Minimum rim freeboard','freeboard_min_in','in'),
        ('Waterline length','waterline_length_in','in'),('Wetted area','wetted_area_in2','in²')])
    gm_text = 'unavailable' if result['gm_transverse_in'] is None else f"{result['gm_transverse_in']:.3f} in"
    report = f'# {study_label} NavalToolbox hydrostatics\n\n'
    report += ('**Supplied-row loading — blank component weights excluded by explicit opt-in.**\n\n' if unresolved else '')
    report += summary + f'\n- Initial transverse GM: {gm_text}\n\n'
    report += f'Whole-boat CAD CG (X/Y/Z): {cg_cad_in[0]:.5f}, {cg_cad_in[1]:.5f}, {cg_cad_in[2]:.5f} in.\n\n'
    report += '![Hydrostatics profile and results](hydrostatics.png)\n\n'
    report += '## Assumptions and loading scope\n\n' + '\n'.join('- '+s for s in assumptions)+'\n\n'
    if unresolved:
        report += 'Excluded blank rows: ' + ', '.join(r['component'] for r in unresolved) + '.\n\n'
    report += '## Numerical checks\n\n'
    report += f"Mesh/STEP volume difference: {geometry['relative_volume_error']:.5%}. Mass-balance error: {balance_error:.5%}. Maximum analytical-box error: {max(benchmark.values()):.5%}. These checks establish numerical consistency, not physical validation.\n\n"
    report += '[CSV results](hydrostatics.csv) · [Full inputs, assumptions and checks](study.json) · [Original loading snapshot](component-masses-input.csv)\n'
    (output/'REPORT.md').write_text(report)
    print('Saved results:', output.relative_to(ROOT) if output.is_relative_to(ROOT) else output)

    return output
