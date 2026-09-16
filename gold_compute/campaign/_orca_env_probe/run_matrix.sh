#!/usr/bin/env bash
# ORCA MPI crash experiment driver
# usage: run_matrix.sh <label> <inp_basename> "<ENV=V ...>"
# runs in /tmp/orca_mpi_probe, appends to matrix_results.csv
set -u
label="$1"; inp="$2"; envspec="${3:-}"
ORCA=/Users/cloudrayyy/opt/orca_6_1_1/orca
cd /tmp/orca_mpi_probe || exit 9
rm -f "${label}.out"
start=$(date +%s)
if [ -z "$envspec" ]; then
  $ORCA "$inp" > "${label}.out" 2>&1
else
  env $envspec $ORCA "$inp" > "${label}.out" 2>&1
fi
rc=$?
end=$(date +%s)
term=$(grep -c "TERMINATED NORMALLY" "${label}.out" 2>/dev/null)
crash=$(grep -c -i -E "segmentation|SIGSEGV|Segmentation fault|bus error|abort|ERROR \(SHARK\)|error termination|failed!" "${label}.out" 2>/dev/null)
sp=$(grep -c "SCF Response" "${label}.out" 2>/dev/null)
printf "%s,%s,rc=%s,%ss,term=%s,crash=%s,env=[%s]\n" "$label" "$inp" "$rc" "$((end-start))" "$term" "$crash" "$envspec" | tee -a /tmp/orca_mpi_probe/matrix_results.csv
