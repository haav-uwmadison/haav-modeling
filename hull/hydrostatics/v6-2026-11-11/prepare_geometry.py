"""Prepare v6 flotation geometry using the v5 meshing and validation workflow.

Requires requirements-geometry.txt. Source bytes are hash-locked to the reviewed
v6 export; the invalid raw rim face is replaced by a new cap from its outer wire.
"""
import collections
import hashlib
import json
import math
import struct
import sys
from pathlib import Path
import OCP.OCP as oc

root = next(p for p in Path(__file__).resolve().parents if (p / 'prop_motor_battery').is_dir())
source = root / 'hull/hydrostatics/v6-2026-11-11/hull 11-11-26.step'
output = root / 'hull/hydrostatics/v6-2026-11-11/geometry'
expected = 'd474db2d427a08451baf3d429c8cdc7846aa81098783ee0c12624f73d6a209f0'
assert hashlib.sha256(source.read_bytes()).hexdigest() == expected, 'Review changed STEP before selecting faces.'

def explore(shape, kind):
    it = oc.TopExp.TopExp_Explorer(shape, kind)
    while it.More():
        yield it.Current()
        it.Next()

def bounds(shape):
    box = oc.Bnd.Bnd_Box()
    oc.BRepBndLib.BRepBndLib.AddOptimal_s(shape, box, False, False)
    lo, hi = box.CornerMin(), box.CornerMax()
    return [[lo.X(), lo.Y(), lo.Z()], [hi.X(), hi.Y(), hi.Z()]]

def naval(point):
    return (point.Y()/1000, -point.X()/1000, point.Z()/1000)

reader = oc.STEPControl.STEPControl_Reader()
assert reader.ReadFile(str(source)) == oc.IFSelect.IFSelect_RetDone
reader.TransferRoots()
shape = reader.OneShape()
# Raw STEP rim face 46 is invalid; reviewed exterior faces are checked below.
source_valid = oc.BRepCheck.BRepCheck_Analyzer(shape).IsValid()
faces = [oc.TopoDS.TopoDS.Face(f) for f in explore(shape, oc.TopAbs.TopAbs_FACE)]
assert len(faces) == 90
audit = []
for i, face in enumerate(faces):
    p = oc.GProp.GProp_GProps()
    oc.BRepGProp.BRepGProp.SurfaceProperties_s(face, p)
    c = p.CentreOfMass()
    audit.append(dict(index=i, valid=bool(oc.BRepCheck.BRepCheck_Analyzer(face).IsValid()), surface=str(oc.BRepAdaptor.BRepAdaptor_Surface(face).GetType()),
                      area_mm2=p.Mass(), centroid_mm=[c.X(), c.Y(), c.Z()], bounds_mm=bounds(face)))
# Reviewed v6 face audit: exterior bottom 41/42, chines 43/44,
# sides 50/53, transom 51. Other faces include internal ribs and mounts.
# Face 46 is the rim; only its outer wire is used to construct a fresh cap.
exterior_indices = [41, 42, 43, 44, 50, 51, 53]
assert all(oc.BRepCheck.BRepCheck_Analyzer(faces[i]).IsValid() for i in exterior_indices)
assert all(abs(audit[46]['bounds_mm'][j][2] - 304.8) < 1e-5 for j in (0, 1))
assert abs(audit[51]['centroid_mm'][1]) < 1e-5
outer = oc.BRepTools.BRepTools.OuterWire_s(faces[46])
cap = oc.BRepBuilderAPI.BRepBuilderAPI_MakeFace(outer, True).Face()
sew = oc.BRepBuilderAPI.BRepBuilderAPI_Sewing(1e-5)
for f in [*(faces[i] for i in exterior_indices), cap]:
    sew.Add(f)
sew.Perform()
shells = list(explore(sew.SewedShape(), oc.TopAbs.TopAbs_SHELL))
assert len(shells) == 1
solid = oc.BRepBuilderAPI.BRepBuilderAPI_MakeSolid(oc.TopoDS.TopoDS.Shell(shells[0])).Solid()
assert oc.BRepLib.BRepLib.OrientClosedSolid_s(solid)
assert oc.BRepCheck.BRepCheck_Analyzer(solid).IsValid()
p = oc.GProp.GProp_GProps()
oc.BRepGProp.BRepGProp.VolumeProperties_s(solid, p)
exact_volume = p.Mass()/1e9
oc.BRepMesh.BRepMesh_IncrementalMesh(solid, .3, False, .15, True).Perform()
triangles = []
seen = set()
for f in explore(solid, oc.TopAbs.TopAbs_FACE):
    face = oc.TopoDS.TopoDS.Face(f)
    loc = oc.TopLoc.TopLoc_Location()
    mesh = oc.BRep.BRep_Tool.Triangulation_s(face, loc)
    assert mesh is not None
    for i in range(1, mesh.NbTriangles()+1):
        triangle = mesh.Triangle(i)
        ids = [triangle.Value(j) for j in (1, 2, 3)]
        if face.Orientation() == oc.TopAbs.TopAbs_REVERSED:
            ids.reverse()
        tri = tuple(tuple(round(v, 8) for v in naval(mesh.Node(k).Transformed(loc.Transformation()))) for k in ids)
        key = tuple(sorted(tri))
        if len(set(tri)) == 3 and key not in seen:
            seen.add(key)
            triangles.append(tri)
edges = collections.Counter()
directions = collections.Counter()
volume = 0.0
for a, b, c in triangles:
    for u, v in [(a,b),(b,c),(c,a)]:
        edge = tuple(sorted((u,v)))
        edges[edge] += 1
        directions[edge] += 1 if (u,v) == edge else -1
    volume += (a[0]*(b[1]*c[2]-b[2]*c[1]) + a[1]*(b[2]*c[0]-b[0]*c[2]) + a[2]*(b[0]*c[1]-b[1]*c[0]))/6
assert all(n == 2 for n in edges.values()), 'Mesh is not watertight.'
assert all(n == 0 for n in directions.values()), 'Inconsistent triangle winding.'
assert volume > 0
error = abs(volume/exact_volume-1)
assert error < .001
rim = []
for e in explore(outer, oc.TopAbs.TopAbs_EDGE):
    curve = oc.BRepAdaptor.BRepAdaptor_Curve(oc.TopoDS.TopoDS.Edge(e))
    for i in range(81):
        t = curve.FirstParameter()+(curve.LastParameter()-curve.FirstParameter())*i/80
        rim.append(naval(curve.Value(t)))
assert all(abs(p[2]-.3048) < 1e-6 for p in rim)
vertices = [p for tri in triangles for p in tri]
mesh_bounds = [[min(p[j] for p in vertices) for j in range(3)], [max(p[j] for p in vertices) for j in range(3)]]
assert math.isclose(mesh_bounds[1][0]-mesh_bounds[0][0],1.8288,abs_tol=1e-5)
assert math.isclose(mesh_bounds[1][2]-mesh_bounds[0][2],.3048,abs_tol=1e-5)
output.mkdir(parents=True, exist_ok=True)
target = output/'hull-envelope.stl'
with target.open('wb') as stream:
    stream.write(b'v6 capped exterior; metres'.ljust(80,b'\0'))
    stream.write(struct.pack('<I',len(triangles)))
    for tri in triangles:
        stream.write(struct.pack('<12fH',0,0,0,*(v for p in tri for v in p),0))
report = dict(source=str(source.relative_to(root)),source_sha256=expected,
              stl_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
              axes='Naval X = CAD Y; naval Y = -CAD X; Z up; metres, full scale.',
              source_valid=source_valid, exterior_face_indices=exterior_indices,cap='Outer wire of planar rim face 46, at CAD Z=12 inches',
              face_audit=audit,watertight=True,winding_consistent=True,triangles=len(triangles),
              bounds_m=mesh_bounds,exact_envelope_volume_m3=exact_volume,mesh_volume_m3=volume,
              relative_volume_error=error,
              assumption='Dry interior; artificial cap at 12-inch rim. No additional tube or appendage buoyancy. Invalid when rim immersed.')
(output/'deck-edge.json').write_text(json.dumps(rim,indent=2)+'\n')
(output/'geometry-report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='face_audit'},indent=2))
