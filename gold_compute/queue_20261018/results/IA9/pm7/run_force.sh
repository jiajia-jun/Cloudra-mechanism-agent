#!/bin/bash
set -e
export OMP_NUM_THREADS=1
MOPAC='/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/gold_compute/queue_20261018/results/IB9/mopac_env/bin/mopac'
"$MOPAC" R_force.mop
"$MOPAC" CH2O_force.mop
