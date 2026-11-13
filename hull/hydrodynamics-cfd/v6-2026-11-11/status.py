"""Print a short progress table for a running or finished ramp case: python3 status.py <case>"""
import glob, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import postprocess as p

case = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.')
wl = sorted(glob.glob(str(case / 'postProcessing/waterLevel/*')), key=lambda d: float(d.rsplit('/', 1)[1]))
print('far-field water level (start 0.1608 m):')
for d in wl[::max(1, len(wl) // 5)] + wl[-1:]:
    t = float(d.rsplit('/', 1)[1])
    print(f'  t={t:6.2f} s  {p.speed_at(case, t):5.2f} mph  upstream {p.surface_height(d + "/upstream.xy"):.4f}'
          f'  downstream {p.surface_height(d + "/downstream.xy"):.4f}')
body = p.rows(glob.glob(str(case / 'postProcessing/rigidBodyState/*/hull.dat'))[0])
forces = {r[0]: r for r in p.rows(glob.glob(str(case / 'postProcessing/forces/*/forces.dat'))[0])}
print('boat (whole-boat forces):')
for r in body[::max(1, len(body) // 8)] + body[-1:]:
    f = forces.get(r[0])
    drag = -2 * (f[1] + f[4]) if f else float('nan')
    lift = 2 * (f[3] + f[6]) if f else float('nan')
    print(f'  t={r[0]:6.3f} s  {p.speed_at(case, r[0]):5.2f} mph  trim {r[5]:6.3f} deg  '
          f'rise {(r[3] - p.REST_Z) * 1000:6.1f} mm  drag {drag:7.2f} N  lift {lift:7.1f} N')
