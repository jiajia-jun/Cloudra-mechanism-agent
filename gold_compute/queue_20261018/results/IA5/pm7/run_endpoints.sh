#!/bin/bash
set -eu
export OMP_NUM_THREADS=1
MOPAC=/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/gold_compute/queue_20261018/results/IB9/mopac_env/bin/mopac
"$MOPAC" rc.mop
"$MOPAC" p.mop
