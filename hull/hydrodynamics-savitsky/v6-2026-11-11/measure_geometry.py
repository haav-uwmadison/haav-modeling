"""Measure the November 11 hull and loading reused from v6 hydrostatics.

Adapts v4's exact boundary-curve sampling to the reviewed v6 exterior faces.
No hydrodynamic solve is run. Requires requirements-geometry.txt from hydrostatics.
"""
import csv
import hashlib
import json
import math
from pathlib import Path
import OCP.OCP as oc

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'prop_motor_battery').is_dir())
HYDRO = ROOT / 'hull/hydrostatics/v6-2026-11-11'


def explore(shape, kind):
    it = oc.TopExp.TopExp_Explorer(shape, kind)
    while it.More():
        yield it.Current()
        it.Next()


def xyz(point):
    return [point.X()/25.4, point.Y()/25.4, point.Z()/25.4]


def at_station(curve, station):
    """v4's bisection on the exact CAD edge, in inches."""
    lo, hi = curve.FirstParameter(), curve.LastParameter()
    increasing = curve.Value(hi).Y() > curve.Value(lo).Y()
    for _ in range(70):
        mid = (lo+hi)/2
        if (curve.Value(mid).Y()/25.4 < station) == increasing:
            lo = mid
        else:
            hi = mid
    point = xyz(curve.Value((lo+hi)/2))
    if abs(point[1]-station) > 1e-6:
        raise ValueError('Station did not converge.')
    return point


def measure():
    geometry = json.loads((HYDRO/'geometry/geometry-report.json').read_text())
    source = ROOT / geometry['source']
    if hashlib.sha256(source.read_bytes()).hexdigest() != geometry['source_sha256']:
        raise ValueError('STEP changed: review hydrostatics face selection first.')
    if geometry['exterior_face_indices'] != [41, 42, 43, 44, 50, 51, 53]:
        raise ValueError('Reviewed v6 topology changed.')
    reader = oc.STEPControl.STEPControl_Reader()
    if reader.ReadFile(str(source)) != oc.IFSelect.IFSelect_RetDone:
        raise ValueError('Could not read STEP.')
    reader.TransferRoots()
    shape = reader.OneShape()
    faces = [oc.TopoDS.TopoDS.Face(f) for f in explore(shape, oc.TopAbs.TopAbs_FACE)]
    if len(faces) != 90:
        raise ValueError('Unexpected v6 face count.')
    if not all(oc.BRepCheck.BRepCheck_Analyzer(faces[i]).IsValid()
               for i in geometry['exterior_face_indices']):
        raise ValueError('Invalid exterior face.')

    curves = {'keel': [], 'inner_chine': [], 'outer_chine': []}
    for index in [42, 44]:
        for edge in explore(faces[index], oc.TopAbs.TopAbs_EDGE):
            curve = oc.BRepAdaptor.BRepAdaptor_Curve(oc.TopoDS.TopoDS.Edge(edge))
            a, b = [xyz(curve.Value(t)) for t in [curve.FirstParameter(), curve.LastParameter()]]
            if a[1] > b[1]:
                a, b = b, a
            if b[1]-a[1] < 1:
                continue
            if index == 42 and abs(a[0]) < 1e-6 and abs(b[0]) < 1e-6:
                name = 'keel'
            elif index == 42 and abs(a[1]) < 1e-6 and a[0] > 0:
                name = 'inner_chine'
            elif index == 44 and abs(a[1]) < 1e-6 and abs(a[0]-8) < 1e-6:
                name = 'outer_chine'
            else:
                continue
            curves[name].append((a[1], b[1], curve))
    if [len(curves[n]) for n in ['keel', 'inner_chine', 'outer_chine']] != [2, 1, 1]:
        raise ValueError('Reviewed v6 exterior edges not found.')

    def point(name, station):
        for lo, hi, curve in curves[name]:
            if lo-1e-7 <= station <= hi+1e-7:
                return at_station(curve, station)
        raise ValueError(f'No {name} edge at {station} inches.')

    sections = []
    for station in [0, 6, 12, 18, 24, 30, 36, 38, 42, 48, 54, 60, 66, 70]:
        k, i, o = [point(n, station) for n in ['keel', 'inner_chine', 'outer_chine']]
        sections.append(dict(station_forward_of_transom_in=station,
            outer_chine_beam_in=2*o[0], main_v_beam_in=2*i[0], keel_z_in=k[2],
            outer_chine_z_in=o[2], inner_chine_z_in=i[2],
            main_v_chord_deg=math.degrees(math.atan2(i[2]-k[2], i[0]-k[0])),
            outer_chine_chord_deg=math.degrees(math.atan2(o[2]-k[2], o[0]-k[0])),
            reverse_chine_chord_deg=math.degrees(math.atan2(o[2]-i[2], o[0]-i[0]))))
    transom_edges = []
    for edge in explore(faces[51], oc.TopAbs.TopAbs_EDGE):
        curve = oc.BRepAdaptor.BRepAdaptor_Curve(oc.TopoDS.TopoDS.Edge(edge))
        transom_edges.append([xyz(curve.Value(curve.FirstParameter()+
            (curve.LastParameter()-curve.FirstParameter())*j/100)) for j in range(101)])
    loading_file = HYDRO/'component-masses.csv'
    included, excluded = [], []
    for line, row in enumerate(csv.DictReader(loading_file.open(newline='')), 2):
        if not row['mass_lbs'].strip():
            if any(row[k].strip() for k in ['cg_x_in', 'cg_y_in', 'cg_z_in']):
                raise ValueError('CG supplied without mass.')
            excluded.append(dict(csv_line=line, **row))
        else:
            vals = [float(row[k]) for k in ['mass_lbs', 'cg_x_in', 'cg_y_in', 'cg_z_in']]
            if vals[0] <= 0 or not all(math.isfinite(v) for v in vals):
                raise ValueError('Invalid loading row.')
            included.append(row)
    total = sum(float(r['mass_lbs']) for r in included)
    if total <= 0:
        raise ValueError('No supplied masses.')
    cg = [sum(float(r['mass_lbs'])*float(r[k]) for r in included)/total
          for k in ['cg_x_in', 'cg_y_in', 'cg_z_in']]
    transom = sections[0]
    inner_half = transom['main_v_beam_in']/2
    outer_half = transom['outer_chine_beam_in']/2
    strip_rise = transom['outer_chine_z_in']-transom['inner_chine_z_in']
    bounds = geometry['bounds_m']
    dims = dict(overall_length=(bounds[1][0]-bounds[0][0])/.0254,
                maximum_overall_beam=(bounds[1][1]-bounds[0][1])/.0254,
                exterior_height=(bounds[1][2]-bounds[0][2])/.0254,
                transom_top_beam=max(p[0] for e in transom_edges for p in e)-min(p[0] for e in transom_edges for p in e),
                outer_chine_beam=2*outer_half, main_v_beam=2*inner_half,
                reverse_chine_strip_each=math.hypot(outer_half-inner_half, strip_rise))
    report = dict(status='CAD dimensions and loading only; user confirmations recorded separately in savitsky-inputs.json.',
        source=str(source.relative_to(ROOT)), source_sha256=geometry['source_sha256'],
        hydrostatics_geometry_report=str((HYDRO/'geometry/geometry-report.json').relative_to(ROOT)),
        source_valid=geometry['source_valid'], exterior_face_indices=geometry['exterior_face_indices'],
        axes='CAD X transverse; Y forward from transom; Z above aft keel',
        dimensions_in=dims, sections=sections, transom_edges_xyz_in=transom_edges,
        proposed_b_m=2*outer_half*.0254,
        deadrise_candidates_deg=dict(main_v=transom['main_v_chord_deg'], outer_chine_chord=transom['outer_chine_chord_deg']),
        mass_file=str(loading_file.relative_to(ROOT)),mass_file_sha256=hashlib.sha256(loading_file.read_bytes()).hexdigest(),
        total_mass_lb=total,total_mass_kg=total*.45359237,cg_xyz_in=cg,
        cg_longitudinal_m=cg[1]*.0254,cg_vertical_m=cg[2]*.0254,
        blank_mass_rows_excluded=excluded,
        notes=['Reuse supplied v6 STEP and loading directly; do not copy or change hydrostatics geometry.',
               'Raw STEP rim is invalid; the selected exterior faces are valid and hydrostatics has a valid capped envelope.',
               'Savitsky uses equivalent-V dimensions, not the flotation mesh as a hydrodynamic solver.',
               'Reverse chine and varying sections/rocker are not explicitly represented by the constant-V engine.',
               'No uniform aft region is established; a straight aft keel segment alone is insufficient.',
               'Small transverse CG offset is omitted by the symmetric Savitsky engine.',
               'Motor CG locations are not thrust-line coordinates. Confirm thrust line separately.'])
    (HERE/'geometry-review.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    with (HERE/'sections.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(sections[0]));writer.writeheader();writer.writerows(sections)
    return report


def make_review_drawing(r):
    """Plot the measured transom for dimension confirmation; requires matplotlib."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    d = r['dimensions_in']
    fig,ax=plt.subplots(figsize=(9,6),layout='constrained')
    for edge in r['transom_edges_xyz_in']:
     ax.plot([p[0] for p in edge],[p[2] for p in edge],color='#344553',lw=2)
    for width,z,label,color in [(d['transom_top_beam'],13.3,'Overall / transom top: 20.341 in','#344553'),(d['outer_chine_beam'],-1.1,'Savitsky b: 16.000 in (outer chine)','#147dbc'),(d['main_v_beam'],-2.7,'Main V width: 14.008 in','#71845c')]:
     ax.annotate('',xy=(width/2,z),xytext=(-width/2,z),arrowprops=dict(arrowstyle='<->',color=color,lw=1.5))
     ax.text(0,z+.3,label,ha='center',color=color,fontsize=10)
    ax.annotate('Main panel: 15°',xy=(4,4*math.tan(math.radians(r['deadrise_candidates_deg']['main_v']))),xytext=(2,5),arrowprops=dict(arrowstyle='->',color='#344553'),fontsize=11)
    ax.annotate('1 in reverse-chine strip\n−5° outward',xy=(7.5,1.83),xytext=(7,6),ha='center',arrowprops=dict(arrowstyle='->',color='#344553'),fontsize=10)
    ax.text(0,9.8,'Exterior height: 12 in\nOverall length: 72 in',ha='center',fontsize=11)
    ax.set(xlim=(-12,12),ylim=(-4,15),aspect='equal',xlabel='Transverse from centerline (in)',ylabel='Above aft keel (in)',title='November 11 v6 — transom dimensions for confirmation')
    ax.grid(alpha=.12)
    fig.savefig(HERE/'geometry-review.png',dpi=160)
    plt.close(fig)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plot', action='store_true', help='Also regenerate geometry-review.png (requires matplotlib).')
    args = parser.parse_args()
    r=measure()
    if args.plot:
        make_review_drawing(r)
    print(json.dumps({k:r[k] for k in ['dimensions_in','deadrise_candidates_deg','total_mass_lb','cg_xyz_in']},indent=2))
