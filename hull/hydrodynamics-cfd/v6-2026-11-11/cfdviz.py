"""Shared loading/rendering helpers for the v6 CFD ramp outputs (used by viewer.py)."""
import pathlib
import numpy as np
import pyvista as pv
import postprocess

HERE = pathlib.Path(__file__).resolve().parent
CASE = HERE / 'results-ramp20'
WATERLINE = 0.1608
RHO_WATER, RHO_AIR, G = 998.2, 1.196, 9.81
SIDE_VIEW = [(-2.2, -3.6, 1.4), (0.9, 0, 0.1), (0, 0, 1)]


def read_vtk(path):
    """Read OpenFOAM's legacy ASCII VTK surfaces. (VTK's own reader drops the data arrays when a
    value is below the float32 range, e.g. 1.4e-45, which OpenFOAM writes for near-zero numbers.)"""
    tok = pathlib.Path(path).read_text().split()
    i = tok.index('POINTS'); n = int(tok[i + 1])
    pts = np.array(tok[i + 3:i + 3 + 3 * n], float).reshape(n, 3)
    j = tok.index('POLYGONS'); size = int(tok[j + 2])
    mesh = pv.PolyData(pts, np.array(tok[j + 3:j + 3 + size], int))
    k = tok.index('FIELD') + 3
    for _ in range(int(tok[k - 1])):
        name, ncomp, ntup = tok[k], int(tok[k + 1]), int(tok[k + 2])
        vals = np.array(tok[k + 4:k + 4 + ncomp * ntup], float)
        mesh[name] = vals.reshape(ntup, ncomp) if ncomp > 1 else vals
        k += 4 + ncomp * ntup
    return mesh


def frames(case=CASE):
    anim = case / 'postProcessing' / 'animation'
    fr = sorted((d for d in anim.iterdir() if d.is_dir()), key=lambda d: float(d.name))
    log = case / 'log.foamRun'
    finished = log.exists() and log.read_text(errors='replace').rstrip().endswith('End')
    return fr if finished else fr[:-1]   # newest frame may still be being written


def load_frame(d, window=(-4, 4, -2.5, 0.01)):
    """Whole boat (half model mirrored); hull gauge pressure in kPa, water-surface elevation in mm."""
    hull = read_vtk(d / 'hull.vtk')
    rho = hull['alpha.water'] * RHO_WATER + (1 - hull['alpha.water']) * RHO_AIR
    hull['pressure_kPa'] = (hull['p_rgh'] - rho * G * hull.points[:, 2]) / 1000
    hull = hull.merge(hull.reflect((0, 1, 0), point=(0, 0, 0)))
    fs = read_vtk(d / 'freeSurface.vtk').clip_box([*window, -1, 1], invert=False)
    fs['elevation_mm'] = (fs.points[:, 2] - WATERLINE) * 1000
    fs = fs.merge(fs.reflect((0, 1, 0), point=(0, 0, 0)))
    return hull, fs


class Labeller:
    def __init__(self, case=CASE):
        self.case = case
        body = postprocess.rows(next((case / 'postProcessing').glob('rigidBodyState/*/hull.dat')))
        self.t = np.array([r[0] for r in body]); self.trim = np.array([r[5] for r in body])
        self.rise = np.array([(r[3] - postprocess.REST_Z) * 1000 for r in body])

    def __call__(self, d):
        t = float(d.name); k = np.argmin(abs(self.t - t))
        return (f't = {t:5.2f} s    {postprocess.speed_at(self.case, t):5.2f} mph    '
                f'trim {self.trim[k]:4.1f}°    rise {self.rise[k]:+5.1f} mm')
