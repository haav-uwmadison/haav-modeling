#!/bin/sh
# Pull the live (or finished) ramp-run outputs from the server to this Mac and
# write ParaView time-series files. Safe to run at any time; it only reads from the server.
#
#   sh sync_results.sh            # motion, forces, water level, animation surfaces
#   sh sync_results.sh --fields   # also the full 3D fields (large: ~110 MB per 0.5 s)
#
# Then:  python3 postprocess.py summary results-ramp20   -> results.csv / results.png
#        open results-ramp20/animation/*.vtk.series in ParaView
set -e
cd "$(dirname "$0")"
REMOTE=server:OpenFOAM/patrickgrunklee-14/run/hav-v6-ramp20
OUT=results-ramp20
mkdir -p "$OUT"
rsync -a "$REMOTE/postProcessing/" "$OUT/postProcessing/"
rsync -a "$REMOTE/log.foamRun" "$OUT/" 2>/dev/null || true
cp speed-schedule.csv "$OUT/"
if [ "${1:-}" = "--fields" ]; then
  rsync -a --include='processor*/' --include='processor*/[0-9]*/***' --include='processor*/constant/***' \
        --include='system/***' --include='constant/***' --exclude='*' "$REMOTE/" "$OUT/case/"
  touch "$OUT/case/case.foam"
  echo "Full fields: open $OUT/case/case.foam in ParaView and set Case Type = Decomposed Case"
fi
python3 - "$OUT" <<'EOF'
import json, pathlib, sys
out = pathlib.Path(sys.argv[1])
anim = out / 'postProcessing' / 'animation'
dest = out / 'animation'; dest.mkdir(exist_ok=True)
times = sorted((d for d in anim.iterdir() if d.is_dir()), key=lambda d: float(d.name))
for name in ('freeSurface', 'hull'):
    files = [dict(name=str((d / f'{name}.vtk').resolve()), time=float(d.name))
             for d in times if (d / f'{name}.vtk').exists()]
    (dest / f'{name}.vtk.series').write_text(json.dumps({'file-series-version': '1.0', 'files': files}, indent=1))
    print(f'{name}: {len(files)} frames, t = {files[0]["time"]}..{files[-1]["time"]} s')
EOF
