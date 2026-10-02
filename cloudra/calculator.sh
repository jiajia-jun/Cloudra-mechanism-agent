#!/bin/bash
# Cloudra 默认计算任务入口脚本。
# 该脚本被 cloudra.compute_utils.launch_compute_processes 调用，
# 负责根据 job_type 在输入文件所在目录下启动对应的外部计算程序。
#
# 用法：
#   calculator.sh <input_file> <job_type> [xtb 任务参数]
#
# 其中 job_type 支持：gaussian, vasp, orca, cp2k, xtb
# job_type=xtb 时透传显式任务参数：
#   --chrg N --uhf M --task sp|opt|hess|ohess --parallel N [--alpb NAME]
#
# 注意：
# - 本脚本不捕获/重定向 stdout/stderr，计算软件自身会写日志。
# - 可执行文件查找：优先系统 PATH（gaussian/cp2k/orca/vasp），
#   运行目录下的本地副本（./orca、./vasp_std 等）仅作兜底。

set -e

INPUT_FILE="$1"
JOB_TYPE="$2"

if [ -z "$INPUT_FILE" ] || [ -z "$JOB_TYPE" ]; then
    echo "用法: calculator.sh <input_file> <job_type> [xtb: --chrg N --uhf M --task T --parallel N [--alpb NAME]]" >&2
    exit 1
fi

if [ ! -f "$INPUT_FILE" ]; then
    echo "输入文件不存在: $INPUT_FILE" >&2
    exit 1
fi

shift 2

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

_resolve_symlink_chain() {
    # 把符号链接链展开为真实文件的绝对路径并打印；任一环节失败（悬挂链接、
    # 目录不可达）返回非零。纯 POSIX 展开：不依赖 GNU readlink -f（macOS 无
    # 此选项），也不依赖 python3（guard 环境未必有）。
    local path="$1"
    local link dir
    while [ -L "$path" ]; do
        link=$(readlink "$path") || return 1
        case "$link" in
            /*) path="$link" ;;
            *)
                dir=$(cd "$(dirname "$path")" 2>/dev/null && pwd) || return 1
                path="$dir/$link"
                ;;
        esac
    done
    [ -e "$path" ] || return 1
    dir=$(cd "$(dirname "$path")" 2>/dev/null && pwd) || return 1
    printf '%s/%s\n' "$dir" "$(basename "$path")"
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
        # command -v 对悬挂符号链接也报找不到（bash 要求可执行）：手工扫 PATH
        # 找回同名条目，交给下方解析/调用阶段给出明确诊断（解析失败回退裸调用，
        # exec 悬挂链接失败按 127 传播，而不是误报"未安装 orca"，GH #15）。
        local _dir
        for _dir in ${PATH//:/ }; do
            if [ -L "$_dir/orca" ] || [ -e "$_dir/orca" ]; then
                orca_bin="$_dir/orca"
                break
            fi
        done
        if [ -z "$orca_bin" ]; then
            echo "系统 PATH 中未找到 orca，运行目录 $WORKDIR 下也无 ./orca 本地副本。" \
                 "请安装 ORCA 并确保 orca 命令在 PATH 中可用，或将 orca 复制到作业目录。" >&2
            exit 1
        fi
    fi

    # 解析符号链接链到真实安装路径，并把真实目录 prepend 到 PATH：
    # 并行 ORCA 拒绝裸名启动（"For parallel runs ORCA has to be called with
    # full pathname"，exit 126），helpers（orca_util/orca_scf/...）也按 orca
    # 可执行文件所在目录定位——conda 符号链接场景两者都会踩（GH #15）。
    # 解析失败（悬挂链接等）时回退裸调用，维持修复前行为。
    local orca_resolved
    if orca_resolved=$(_resolve_symlink_chain "$orca_bin"); then
        orca_bin="$orca_resolved"
        export PATH="$(dirname "$orca_bin"):$PATH"
        echo "[calculator] orca resolved: $orca_bin" >&2
    else
        echo "[calculator] orca 路径解析失败，回退裸调用: $orca_bin" >&2
    fi
    # 显式传播 orca 退出码：bash 3.2（macOS 自带）在 set -e 语义下（含 || 捕获）
    # 会把命令失败的状态统一改写成 1，吞掉 exec 失败的 127 与 orca 真实退出码；
    # 只能暂时关 set -e 取到真实状态再退出（GH #15）。
    #
    # WORKDIR 已切到输入目录。总是用同目录 basename：既避免 ORCA 对
    # 含空白父路径拆词，也避免原生 PropertyIntegralDriver 在长绝对输入
    # 参数下触发栈溢出（相同输入字节的真实 A/B：绝对参数 SIGABRT，basename 正常）。
    # 二进制仍用真实完整路径，满足并行启动要求；原始输入和证据路径不变。
    # basename 本身含空白时继续使用作业目录内的硬链接安全名，并在日志留映射。
    local input_arg
    input_arg=$(basename "$INPUT_FILE")
    local safe_input_name=""
    case "$input_arg" in
        *[[:space:]]*)
            safe_input_name=$(printf '%s' "$input_arg" | tr '[:space:]' '_')
            safe_input_name=".cloudra_orasafe_$$_$safe_input_name"
            ln "$INPUT_FILE" "$WORKDIR/$safe_input_name"
            input_arg="$safe_input_name"
            echo "[calculator] orca input mapped to safe execution name: $safe_input_name (original: $INPUT_FILE)" >&2
            ;;
    esac
    set +e
    "$orca_bin" "$input_arg"
    local orca_status=$?
    set -e
    if [ -n "$safe_input_name" ]; then
        rm -f "$WORKDIR/$safe_input_name" || true
    fi
    [ "$orca_status" -eq 0 ] || exit "$orca_status"
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

run_xtb() {
    # xtb 是 CLI 标志驱动：输入文件即 .xyz 坐标文件（无输入文件格式），主输出
    # 走 stdout、自身不落日志文件，且终止标记（normal termination of xtb）
    # 打印在 stderr——stdout+stderr 一并重定向到 <输入stem>.out，与
    # compute_utils.get_log_path 的推导保持一致（参照 run_cp2k 的 -o 语义）。
    #
    # 任务参数由 guard 按 compute_jobs 行的 xtb 列透传（submit 时已校验）：
    #   --chrg N --uhf M --task sp|opt|hess|ohess --parallel N [--alpb NAME]
    # 电荷/多重度只认这里的显式声明：xtb 会忽略 xyz 注释行里的 charge/mult
    # （job 130 静默科学错误的根因），缺省也显式拼 --chrg 0 --uhf 0。
    if ! command -v xtb >/dev/null 2>&1; then
        echo "系统 PATH 中未找到 xtb。请安装 xTB 并确保 xtb 命令在 PATH 中可用。" >&2
        exit 1
    fi
    local output="${INPUT_FILE%.*}.out"
    local chrg=0 uhf=0 task="sp" parallel=1 alpb=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --chrg) chrg="$2"; shift 2 ;;
            --uhf) uhf="$2"; shift 2 ;;
            --task) task="$2"; shift 2 ;;
            --parallel) parallel="$2"; shift 2 ;;
            --alpb) alpb="$2"; shift 2 ;;
            *) echo "run_xtb: 未知参数: $1" >&2; exit 1 ;;
        esac
    done
    local task_flag=""
    case "$task" in
        sp) ;;
        opt) task_flag="--opt" ;;
        hess) task_flag="--hess" ;;
        ohess) task_flag="--ohess" ;;
        *) echo "run_xtb: 不支持的 task: ${task}（支持 sp/opt/hess/ohess）" >&2; exit 1 ;;
    esac
    # 资源申请透传：--parallel 钉 xtb 线程数，同时显式 export OMP_NUM_THREADS
    # 兜底（cpus=1 的申请曾跑出 18 线程，容量记账失效）。
    export OMP_NUM_THREADS="$parallel"
    local args=("$INPUT_FILE" "--chrg" "$chrg" "--uhf" "$uhf" "--parallel" "$parallel")
    [ -n "$task_flag" ] && args+=("$task_flag")
    [ -n "$alpb" ] && args+=("--alpb" "$alpb")
    echo "[calculator] xtb ${args[*]}" >&2
    xtb "${args[@]}" > "$output" 2>&1
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
    chem_task)
        if [ "$#" -ne 2 ] || [ -z "$1" ] || [ -z "$2" ]; then
            echo "chem_task requires the trusted executor Python and module root" >&2
            exit 1
        fi
        "$1" -c 'import sys; sys.path.insert(0,sys.argv[1]); from cloudra.runtime.chem_task import run_task; sys.exit(run_task(sys.argv[2]))' "$2" "$INPUT_FILE"
        ;;
    xtb)
        run_xtb "$@"
        ;;
    *)
        echo "不支持的 job_type: $JOB_TYPE" >&2
        exit 1
        ;;
esac
