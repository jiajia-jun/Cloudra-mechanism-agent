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
# - 本脚本通过系统 PATH 查找外部计算程序，不依赖工作目录下的本地副本。

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
    if [ -x "./orca" ]; then
        ./orca "$INPUT_FILE"
    else
        echo "在当前工作目录 $WORKDIR 中未找到 ORCA 可执行文件（./orca）" >&2
        exit 1
    fi
}

run_vasp() {
    # VASP 读取当前目录下的 INCAR/POSCAR/POTCAR/KPOINTS，不接收输入文件参数
    if [ -x "./vasp_std" ]; then
        ./vasp_std
    elif [ -x "./vasp_gam" ]; then
        ./vasp_gam
    elif [ -x "./vasp_ncl" ]; then
        ./vasp_ncl
    else
        echo "在当前工作目录 $WORKDIR 中未找到 VASP 可执行文件（./vasp_std, ./vasp_gam 或 ./vasp_ncl）" >&2
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
