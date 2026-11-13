"""Read rigid-body motion and hull forces for a v6 planing run.

Usage:
    python3 postprocess.py check <case>      # gate after the 1 s rest test (exit 1 on failure)
    python3 postprocess.py summary <case>    # CSV + plots for the ramp run

Half model: forces are doubled to whole-boat values. Flow is in -x, so drag = -2*Fx.
"""
import csv, json, math, pathlib, sys

HALF_WEIGHT_N = 34.834760035075 * 9.81
REST_TRIM_DEG, REST_Z = 1.807, 0.162535


def rows(path):
    out = []
    for line in open(path):
        if line.startswith('#') or not line.strip():
            continue
        vals = line.replace('(', ' ').replace(')', ' ').split()
        try:
            out.append([float(v) for v in vals])
        except ValueError:
            continue
    return out


def load(case):
    case = pathlib.Path(case)
    pp = case / 'postProcessing'
    body = rows(next(pp.glob('rigidBodyState/*/hull.dat')))
    force = rows(next(pp.glob('forces/*/forces.dat')))
    return case, body, force


def speed_at(case, t):
    pts = [(float(r['time_s']), float(r['speed_mph'])) for r in csv.DictReader(open(case / 'speed-schedule.csv'))]
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        if t0 <= t <= t1:
            return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return pts[-1][1]


def check(case):
    case, body, force = load(case)
    log = (case / 'log.foamRun').read_text(errors='replace')
    problems = []
    t_end = body[-1][0]
    if t_end < 0.99:
        problems.append(f'test stopped early at t={t_end:.3f} s')
    if 'FOAM FATAL' in log or 'Floating point exception' in log or ' nan' in log.lower():
        problems.append('solver error or NaN in log.foamRun')
    trims = [r[5] for r in body]
    zs = [r[3] for r in body]
    if not all(0 < x < 5 for x in trims):
        problems.append(f'trim left 0-5 deg band (min {min(trims):.2f}, max {max(trims):.2f})')
    if not all(0.12 < z < 0.21 for z in zs):
        problems.append(f'CG height left 0.12-0.21 m band (min {min(zs):.4f}, max {max(zs):.4f})')
    late = [r for r in force if r[0] > t_end - 0.2]
    fz = sum(r[3] + r[6] for r in late) / max(len(late), 1)
    if abs(fz / HALF_WEIGHT_N - 1) > 0.10:
        problems.append(f'vertical force {fz:.1f} N vs half weight {HALF_WEIGHT_N:.1f} N (>10% off)')
    result = dict(passed=not problems, problems=problems, t_end=t_end,
                  trim_start=trims[0], trim_end=trims[-1], trim_max=max(trims),
                  z_start=zs[0], z_end=zs[-1], mean_vertical_force_last_0p2s=fz,
                  half_weight=HALF_WEIGHT_N)
    (case / 'test-check.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0 if not problems else 1


def summary(case):
    case, body, force = load(case)
    fmap = {}
    for r in force:
        fmap[r[0]] = r
    out = []
    for r in body:
        f = fmap.get(r[0])
        if f is None:
            continue
        t = r[0]
        out.append(dict(time_s=t, speed_mph=speed_at(case, t), trim_deg=r[5],
                        rise_mm=(r[3] - REST_Z) * 1000,
                        drag_N=-2 * (f[1] + f[4]), lift_N=2 * (f[3] + f[6]),
                        pressure_drag_N=-2 * f[1], friction_drag_N=-2 * f[4]))
    with open(case / 'results.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader(); w.writerows(out)
    try:
        import matplotlib; matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        t = [o['time_s'] for o in out]
        fig, ax = plt.subplots(4, 1, figsize=(9, 11), sharex=True)
        for a, key, label in zip(ax, ['speed_mph', 'trim_deg', 'rise_mm', 'drag_N'],
                                 ['Speed (mph)', 'Trim, bow up (deg)', 'CG rise from rest (mm)', 'Drag, whole boat (N)']):
            a.plot(t, [o[key] for o in out], lw=1)
            a.set_ylabel(label); a.grid(alpha=.3)
        ax[-1].set_xlabel('Simulated time (s)')
        fig.suptitle('v6 hull, towed ramp to 20 mph (OpenFOAM 14, half model)')
        fig.tight_layout(); fig.savefig(case / 'results.png', dpi=130)
    except Exception as e:  # plots are optional; CSV is the record
        print('plotting skipped:', e)
    print(f'wrote {case / "results.csv"} ({len(out)} rows)')
    return 0


WATERLINE = 0.1608
LEVEL_TOL = 0.06          # m; far-field free surface drift that stops the run
Z_BAND = (0.05, 0.40)     # m; CG height
TRIM_BAND = (-5.0, 25.0)  # deg; bow up positive
MIN_DT = 1e-6             # s; time-step collapse = divergence


def surface_height(path):
    pts = []
    for line in open(path):
        v = line.split()
        if len(v) >= 2 and not line.startswith('#'):
            pts.append((float(v[0]), float(v[1])))
    pts.sort()
    for (z0, a0), (z1, a1) in zip(pts[::-1][1:], pts[::-1]):   # scan downward from the top
        if a0 >= 0.5 > a1:
            return z0 + (z1 - z0) * (a0 - 0.5) / (a0 - a1)
    return None


def watch(case):
    """Return non-zero (and print why) if the running case has gone wrong."""
    case = pathlib.Path(case)
    problems = []
    wl = case / 'postProcessing' / 'waterLevel'
    if wl.exists():
        times = sorted((d for d in wl.iterdir() if d.is_dir()), key=lambda d: float(d.name))
        if times:
            latest = times[-1]
            for name in ('upstream', 'downstream'):
                f = next(latest.glob(f'{name}*.xy'), None)
                h = surface_height(f) if f else None
                if h is not None and abs(h - WATERLINE) > LEVEL_TOL:
                    problems.append(f'{name} water level {h:.3f} m at t={latest.name} '
                                    f'(start {WATERLINE}, limit +/-{LEVEL_TOL})')
    try:
        body = rows(next((case / 'postProcessing').glob('rigidBodyState/*/hull.dat')))
        t, z, trim = body[-1][0], body[-1][3], body[-1][5]
        if not Z_BAND[0] < z < Z_BAND[1]:
            problems.append(f'CG height {z:.3f} m at t={t:.3f} outside {Z_BAND}')
        if not TRIM_BAND[0] < trim < TRIM_BAND[1]:
            problems.append(f'trim {trim:.2f} deg at t={t:.3f} outside {TRIM_BAND}')
    except (StopIteration, IndexError):
        pass
    log = case / 'log.foamRun'
    if log.exists():
        dts = [l for l in log.read_text(errors='replace').splitlines()[-400:] if l.startswith('deltaT')]
        if dts and float(dts[-1].split('=')[1]) < MIN_DT:
            problems.append(f'time step collapsed to {dts[-1].split("=")[1].strip()} s')
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == '__main__':
    mode, case = sys.argv[1], sys.argv[2]
    sys.exit({'check': check, 'summary': summary, 'watch': watch}[mode](case))
