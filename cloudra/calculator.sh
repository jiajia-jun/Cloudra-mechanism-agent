#!/bin/bash
# Cloudra 默认计算任务入口脚本。
# 该脚本被 cloudra.compute_utils.launch_compute_processes 调用，
# 负责根据 job_type 在输入文件所在目录下启动对应的外部计算程序。
#
# 用法：
#   calculator.sh <input_file> <job_type>
#
# 其中 job_type 支持：gaussian, vasp, orca, cp2k
#
# 注意：
# - 本脚本不捕获/重定向 stdout/stderr，计算软件自身会写日志。
# - 可执行文件查找：优先系统 PATH（gaussian/cp2k/orca/vasp），
#   运行目录下的本地副本（./orca、./vasp_std 等）仅作兜底。

set -e

INPUT_FILE="$1"
JOB_TYPE="$2"

if [ -z "$INPUT_FILE" ] || [ -z "$JOB_TYPE" ]; then
    echo "用法: calculator.sh <input_file> <job_type>" >&2
    exit 1
fi

if [ ! -f "$INPUT_FILE" ]; then
    echo "输入文件不存在: $INPUT_FILE" >&2
    exit 1
fi

WORKDIR=$(cd "$(dirname "$INPUT_FILE")" && pwd)
cd "$WORKDIR"

run_gaussian() {
    # Gaussian 可执行文件通常命名为 g16/g09/g26。
    # 统一通过系统 PATH 调用，不依赖工作目录下的本地副本。
    #
    # Link0 会把 .gjf 拷到 $GAUSS_SCRDIR/Gau-$PID.inp。多个本地任务若共用
    # 同一个 GAUSS_SCRDIR（常见全局 ~/…/Utsu），并行时会互相踩 rwf/chk/inp，
    # 表现为 Link1 后立刻 FileIO、日志只有一百多行、零 SCF——不是输入写错。
    # guard 已分配 cloudra_g16_* 时直接用；否则自建子目录，EXIT 后再删。
    local base_scr="${GAUSS_SCRDIR:-$WORKDIR/.g16_scratch}"
    local job_scr
    local own_scratch=0
    if [[ "$(basename -- "$base_scr")" == cloudra_g16_* ]]; then
        job_scr="$base_scr"
        mkdir -p "$job_scr"
    else
        mkdir -p "$base_scr"
        job_scr="${base_scr%/}/cloudra_g16_$$"
        mkdir -p "$job_scr"
        own_scratch=1
    fi
    export GAUSS_SCRDIR="$job_scr"
    if [ "$own_scratch" -eq 1 ]; then
        # shellcheck disable=SC2064
        trap "rm -rf -- $(printf '%q' "$job_scr")" EXIT
    fi
    echo "[calculator] isolated GAUSS_SCRDIR=$GAUSS_SCRDIR" >&2

    if command -v g16 >/dev/null 2>&1; then
        g16 "$INPUT_FILE"
    elif command -v g09 >/dev/null 2>&1; then
        g09 "$INPUT_FILE"
    elif command -v g26 >/dev/null 2>&1; then
        g26 "$INPUT_FILE"
    else
        echo "系统 PATH 中未找到 Gaussian 可执行文件（g16/g09/g26）。" \
             "请安装 Gaussian 并确保对应命令在 PATH 中可用。" >&2
        exit 1
    fi
}

run_orca() {
    # ORCA external MLIP（输入含 `%method ProgExt`，如 MACE-OMol25）会把能量/梯度
    # 卸载给 Python 侧的 mace/ase：macOS 上其 libomp 与 ORCA 自带 OpenMP 重复装载
    # 会报 OMP Error #15，且 MACE 需要单线程调用（OMP Error #15 探针见
    # deploy/mace_omol25_orca_external_setup.md §3.1）。仅在输入声明外部 MLIP 时注入，
    # 普通 DFT 任务不设 OMP_NUM_THREADS=1，避免锁死 ORCA 的 OpenMP 线程层。
    if grep -qE 'ExtOpt|ProgExt' "$INPUT_FILE"; then
        export KMP_DUPLICATE_LIB_OK=TRUE
        export OMP_NUM_THREADS=1
        echo "[calculator] MLIP external route detected: KMP_DUPLICATE_LIB_OK=TRUE OMP_NUM_THREADS=1" >&2
    fi

    local orca_bin=""
    if command -v orca >/dev/null 2>&1; then
        orca_bin=$(command -v orca)
    elif [ -x "./orca" ]; then
        orca_bin="$WORKDIR/orca"
    else
        echo "系统 PATH 中未找到 orca，运行目录 $WORKDIR 下也无 ./orca 本地副本。" \
             "请安装 ORCA 并确保 orca 命令在 PATH 中可用，或将 orca 复制到作业目录。" >&2
        exit 1
    fi

    # 解析符号链接链到真实安装路径，并把真实目录 prepend 到 PATH：
    # 并行 ORCA 拒绝裸名启动（"For parallel runs ORCA has to be called with
    # full pathname"，exit 126），helpers（orca_util/orca_scf/...）也按 orca
    # 可执行文件所在目录定位——conda 符号链接场景两者都会踩（GH #15）。
    # POSIX 展开，不依赖 GNU readlink -f（macOS 无此选项）。
    while [ -L "$orca_bin" ]; do
        local link
        link=$(readlink "$orca_bin")
        case "$link" in
            /*) orca_bin="$link" ;;
            *)  orca_bin="$(cd "$(dirname "$orca_bin")" && pwd)/$link" ;;
        esac
    done
    orca_bin="$(cd "$(dirname "$orca_bin")" && pwd)/$(basename "$orca_bin")"
    export PATH="$(dirname "$orca_bin"):$PATH"
    echo "[calculator] orca resolved: $orca_bin" >&2
    "$orca_bin" "$INPUT_FILE"
}

run_vasp() {
    # VASP 读取当前目录下的 INCAR/POSCAR/POTCAR/KPOINTS，不接收输入文件参数。
    # PATH 优先（vasp_std/vasp_gam/vasp_ncl），运行目录本地副本兜底（HPC 惯例）。
    if command -v vasp_std >/dev/null 2>&1; then
        vasp_std
    elif command -v vasp_gam >/dev/null 2>&1; then
        vasp_gam
    elif command -v vasp_ncl >/dev/null 2>&1; then
        vasp_ncl
    elif [ -x "./vasp_std" ]; then
        ./vasp_std
    elif [ -x "./vasp_gam" ]; then
        ./vasp_gam
    elif [ -x "./vasp_ncl" ]; then
        ./vasp_ncl
    else
        echo "系统 PATH 中未找到 VASP 可执行文件（vasp_std/vasp_gam/vasp_ncl），运行目录 $WORKDIR 下也无本地副本。" >&2
        exit 1
    fi
}

run_cp2k() {
    # CP2K 统一通过系统 PATH 查找可执行文件（cp2k.popt/cp2k.ssmp/cp2k.psmp/cp2k），
    # 不依赖工作目录下的本地副本。输出写入与输入文件同名的 .out，
    # 与 compute_utils.get_log_path 的推导保持一致。
    local cp2k_bin=""
    for candidate in cp2k.popt cp2k.ssmp cp2k.psmp cp2k; do
        if command -v "$candidate" >/dev/null 2>&1; then
            cp2k_bin="$candidate"
            break
        fi
    done
    if [ -z "$cp2k_bin" ]; then
        echo "系统 PATH 中未找到 CP2K 可执行文件（cp2k.popt/cp2k.ssmp/cp2k.psmp/cp2k）。" \
             "请安装 CP2K 并确保对应命令在 PATH 中可用。" >&2
        exit 1
    fi
    local output="${INPUT_FILE%.*}.out"
    "$cp2k_bin" -i "$INPUT_FILE" -o "$output"
}

case "$JOB_TYPE" in
    gaussian)
        run_gaussian
        ;;
    orca)
        run_orca
        ;;
    vasp)
        run_vasp
        ;;
    cp2k)
        run_cp2k
        ;;
    *)
        echo "不支持的 job_type: $JOB_TYPE" >&2
        exit 1
        ;;
esac
