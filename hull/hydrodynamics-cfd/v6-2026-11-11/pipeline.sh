#!/bin/bash
# Unattended sequence on the server (run inside tmux session "boat"):
#   1. wait for the 1 s rest test (hav-v6-planing) to finish
#   2. check it (postprocess.py check); stop if it fails
#   3. run the 17 s ramp (hav-v6-ramp20), reusing the test's decomposed mesh
#   4. summarise results; reconstruct fields for ParaView
# Status lines go to ~/OpenFOAM/patrickgrunklee-14/run/PIPELINE_STATUS
source /opt/openfoam14/etc/bashrc >/dev/null 2>&1   # before set -u: the OpenFOAM bashrc uses unset variables
set -u
RUN=$HOME/OpenFOAM/patrickgrunklee-14/run
TEST=$RUN/hav-v6-planing
FULL=$RUN/hav-v6-ramp20
STATUS=$RUN/PIPELINE_STATUS
NP=12
status() { echo "$(date -u +%FT%TZ) $*" | tee -a "$STATUS"; }

# hardware log: per-minute clocks, package temperature and fan speeds
(
  pkg=$(grep -l x86_pkg_temp /sys/class/thermal/thermal_zone*/type | head -1 | xargs dirname)
  fan=$(grep -l dell_smm /sys/class/hwmon/hwmon*/name | head -1 | xargs dirname)
  echo "utc pkg_C fan1 fan2 mean_busy_MHz min_busy_MHz"
  while true; do
    mhz=$(ps -L -o psr=,pcpu= -C foamRun | awk '$2>50{print $1}' | sort -u | while read c; do
            echo $(( $(cat /sys/devices/system/cpu/cpu$c/cpufreq/scaling_cur_freq) / 1000 )); done |
          awk '{s+=$1; if(min==""||$1<min)min=$1; n++} END{if(n) printf "%d %d", s/n, min; else printf "- -"}')
    echo "$(date -u +%T) $(( $(cat $pkg/temp) / 1000 )) $(cat $fan/fan1_input) $(cat $fan/fan2_input) $mhz"
    sleep 60
  done
) >> "$RUN/hardware.log" 2>&1 &
HWLOG=$!
trap 'kill $HWLOG 2>/dev/null' EXIT

status "pipeline started; waiting for rest test"
while pgrep -x foamRun >/dev/null; do sleep 30; done

if ! python3 "$FULL/postprocess.py" check "$TEST" > "$TEST/log.check" 2>&1; then
  status "STOPPED: rest test failed checks (see $TEST/test-check.json)"
  exit 1
fi
status "rest test passed checks"

cd "$FULL" || exit 1
rm -rf postProcessing log.foamRun log.decomposePar log.summary log.reconstructPar
for p in "$TEST"/processor*; do
  d=$(basename "$p"); rm -rf "$d"; mkdir -p "$d"; cp -r "$p/constant" "$d/"
done
decomposePar -fields -copyZero > log.decomposePar 2>&1 || { status "STOPPED: decomposePar failed"; exit 1; }

status "ramp run started (accelerating frame: 0 -> 20 mph over 1-11 s, hold to 16 s)"
mpirun -np $NP foamRun -parallel > log.foamRun 2>&1 &
SOLVER=$!
# watchdog: stop early if the water level drifts, the hull leaves its band, or the time step collapses
while kill -0 $SOLVER 2>/dev/null; do
  sleep 120
  if ! why=$(python3 postprocess.py watch "$FULL" 2>&1); then
    status "WATCHDOG: $why"
    pkill -x foamRun
    wait $SOLVER
    status "STOPPED by watchdog"
    python3 postprocess.py summary "$FULL" > log.summary 2>&1
    exit 1
  fi
done
wait $SOLVER
rc=$?
last=$(grep -a '^Time = ' log.foamRun | tail -1)
if [ $rc -ne 0 ] || ! tail -5 log.foamRun | grep -q '^End'; then
  status "STOPPED: ramp run ended abnormally (exit $rc, $last)"
  python3 postprocess.py summary "$FULL" > log.summary 2>&1
  exit 1
fi
status "ramp run finished ($last)"

python3 postprocess.py summary "$FULL" > log.summary 2>&1 && status "summary written: results.csv, results.png" \
  || status "summary failed (see log.summary)"
reconstructPar > log.reconstructPar 2>&1 && status "fields reconstructed for ParaView" \
  || status "reconstructPar failed (processor data still complete)"
status "pipeline done"
