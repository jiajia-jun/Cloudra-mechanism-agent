#!/bin/bash
set -e
export OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4
/Users/cloudrayyy/miniconda3/envs/chemai/bin/python casscf_sp.py
