#!/usr/bin/env bash
# usage: run_matrix_dir.sh <workdir> <label> <inp_basename> "<ENV=V ...>"
set -u
wd="$1"; label="$2"; inp="$3"; envspec="${4:-}"
ORCA=/Users/cloudrayyy/opt/orca_6_1_1/orca
mkdir -p "$wd"; cd "$wd" || exit 9
cp -f /tmp/orca_mpi_probe/"$inp" "$wd"/ 2>/dev/null
if [ -z "$envspec" ]; then
  $ORCA "$inp" > "$label.out" 2>&1
else
  env $envspec $ORCA "$inp" > "$label.out" 2>&1
fi
rc=$?
term=$(grep -c "TERMINATED NORMALLY" "$label.out" 2>/dev/null)
printf "%s,%s,rc=%s,term=%s,wd=%s,env=[%s]\n" "$label" "$inp" "$rc" "$term" "$wd" "$envspec" >> /tmp/orca_mpi_probe/matrix_dir.csv
