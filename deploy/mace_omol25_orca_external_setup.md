# MACE-OMol25 + ORCA external 计算栈环境配置

> 用途：P1 能垒标定（`gold.reference_computation`，`computed_by_us=true` 的 MACE-OMol25 参考答案）。
> 本文档记录**已核实可复现**的环境配置经验，所有结论均来自本机实跑验证（非推测）。

## 1. 目标与统一口径

- 唯一物理计算金标准 = **MACE-OMol25**（`level_of_theory="MACE-OMol25"`）。
- 能垒基准取 **`central_complex`**（TS 相对反应物/离子-偶极络合物），不取分离渐近线。
- TS 验收：`n_imag==1`（并排除 `<100 cm^-1` 伪低频）+ **双向 IRC 端点连通**；仅找到鞍点不算完成。
- `xTB` 仅作预筛，**不计入参考值**。

## 2. 环境现状（chemai conda env）

| 组件 | 状态 | 说明 |
| :--- | :--- | :--- |
| `mace` | ✅ 0.3.16 | python 包，非 PATH 可执行文件；由 `ProgExt`/ASE 调用 |
| `ase` | ✅ 3.29.0 | mace 依赖 |
| `xtb` | ✅ | `/Users/cloudrayyy/miniconda3/envs/chemai/bin/xtb` |
| `orca` | ✅ | `/Users/cloudrayyy/opt/orca_6_1_1/orca` |
| `orca-mlips-mace` | ✅ | ORCA 的 MLIP 外部工具接口插件（在 PATH） |
| **`g16`** | ❌ **缺失** | 全盘无 g16 |
| **`g16-mlips`** | ❌ **缺失** | 全盘无 g16-mlips |
| `crest` | ❌ | 未装（非必需） |

### 结论：计算引擎路径

任务单指定的 **`Gaussian external="mace"` 协议当前不可用**（缺 g16 + g16-mlips）。

**等价替代路径 = `ORCA external="mace"`**（经 `orca-mlips-mace`），已完成微型验证（见 §5）。
**建议作为首选计算引擎。**

## 3. 关键坑点与解决办法

### 3.1 OMP Error #15（libomp.dylib 重复初始化）

加载 mace/ase 时若报 `OMP Error #15`，需在环境里设置：

```bash
export KMP_DUPLICATE_LIB_OK=TRUE
```

### 3.2 `mace` 不是可执行文件

`command -v mace` 会误报 NOT FOUND。正确判断方式：`python -c "import mace; print(mace.__version__)"`。

### 3.3 ORCA 外部工具接口路径

ORCA 的 `%method` 块里 `ProgExt` 必须指向 **mace 的 python 可执行**（`/Users/cloudrayyy/miniconda3/envs/chemai/bin/mace`），
`Ext_Params` 传模型路径、设备与精度。

### 3.4 ⚠️ 本机 ORCA **从不写 .out 文件**（macOS 构建行为，2026-09-03 实证）

`orca x.inp` 跑完（NORMAL TERMINATION、产物 gbw/engrad/opt/property 齐全）后**不会生成 `x.out`**——
**主输出全部写 stdout**，与官方设计（orca 自建输出文件）不同。已排除的变量：ExtOpt/MLIP 与否、单核/MPI、
stdout 重定向目标（/dev/null/文件/管道/伪 tty）均无关；orca-mlips 只是 `%method ProgExt` 外部工具，不碰此行为。
普通 DFT（B3LYP）作业同样如此，属**此 6.1.1 macOS arm64 构建的平台差异**。

对执行链路的含义：
- **直接跑 orca 时把 stdout 落盘**：`orca x.inp > x.out 2>&1`（x.out 内容即完整主输出，cclib 可正常解析，success=True）；
- **cloudra guard 已适配**（2026-09-03 起）：calculator stdout/stderr 落盘 `.cloudra/calc-<id>.out.log`，
  推导日志缺失/为空时回退解析该文件——无需再手动重定向。

### 3.5 calculator 执行环境是"干净 PATH"

guard/scheduler 由守护进程 detach 拉起，继承启动时的 shell 环境；若服务不在 conda env 里启动，
`command -v orca/mpirun` 找不到。`calculator.sh`（内置或作业目录定制）内负责注入完整 PATH
（orca 目录 + openmpi + conda bin）；guard 的环境检查（`check_job_type`）在 calculator 启动前执行，
同样要求 PATH 可见——**服务须在配置好计算环境的 shell 中启动**，或把所需 bin 加入该 shell 的 PATH。

## 4. ORCA 输入模版（已验证可跑）

**优化（Opt）：**
```orca
! ExtOpt Opt
%pal nprocs 4 end
%maxcore 1024
%method
  ProgExt "/Users/cloudrayyy/miniconda3/envs/chemai/bin/mace"
  Ext_Params "--model /Users/cloudrayyy/opt/mace-omol25/MACE-omol-0-extra-large-1024.model --device cpu --dtype float64"
end
* xyz 0 1
O      0.007544    0.397743    0.000000
H     -0.767103   -0.184393    0.000000
H      0.759559   -0.213350    0.000000
*
```

**频率（Freq，可叠加 Opt 为 `! ExtOpt NumFreq`）：**
```orca
! ExtOpt NumFreq
%pal nprocs 4 end
%maxcore 1024
%method
  ProgExt "/Users/cloudrayyy/miniconda3/envs/chemai/bin/mace"
  Ext_Params "--model /Users/cloudrayyy/opt/mace-omol25/MACE-omol-0-extra-large-1024.model --device cpu --dtype float64"
end
*XYZFILE 0 1 water_geom.xyz
```

## 5. 已验证结果

- 水分子单点/优化经 **ORCA `external="mace"`** 成功收敛：`optdone=true`、`ORCA TERMINATED NORMALLY`。
- MACE 最终单点能量：`-76.43367 Ha`（水，`MACE-omol-0-extra-large-1024.model`）。
- 工作目录：`.cloudra/mace_orca_probe/`，探针输入 `water_geom.inp`，日志 `water_geom.out`。

### 5.1 探针 calculator.sh（环境变量处理范式）

```bash
#!/bin/bash
set -e
INPUT_FILE="$1"; JOB_TYPE="$2"
WORKDIR=$(cd "$(dirname "$INPUT_FILE")" && pwd)
cd "$WORKDIR"

export KMP_DUPLICATE_LIB_OK=TRUE
export OMP_NUM_THREADS=1
export PATH=/Users/cloudrayyy/opt/orca_6_1_1:/Users/cloudrayyy/opt/openmpi-4.1.8/bin:$PATH

if [ -x "./orca" ]; then
    ./orca "$INPUT_FILE"
elif command -v orca >/dev/null 2>&1; then
    orca "$INPUT_FILE"
else
    echo "ORA oracle not found" >&2
    exit 1
fi
```

## 6. 模型权重路径

- **真权重**（探针实际使用）：
  `/Users/cloudrayyy/opt/mace-omol25/MACE-omol-0-extra-large-1024.model`
- **仓库内 `ideapool/mlp_benchmark/models/md_omol25/2025_levine_omol25/2025_levine_omol25.md`
  不是模型二进制** —— 实为 arXiv:2505.08762（OMol25）论文的 Markdown 文本（file 判定 Unicode text），勿当权重使用。

## 7. 关键文件索引

| 文件 | 说明 |
| :--- | :--- |
| `cloudra/skills/dft-calculation/references/mlip-gaussian-external.md` | MLIP external 引擎说明（公用 skill）：Gaussian g16-mlips 通用段 + ORCA `ExtOpt` 路线（qm_input_writer `engine="orca"` 生成；ProgExt/权重路径为部署占位，本机具体值见本文档 §3.3/§6；运行时环境变量已由 `calculator.sh` orca 分支自动注入） |
| `paper/reference_answer_task_P1.md` | P1 能垒标定任务单（具体题号列表在文档后段） |
| `paper/reference_calc_plan.md` | 能垒标定宏观分工计划 |
| `ideapool/tasks/<tier>/<task_id>.json` | 题目定义；回填目标字段 `gold.reference_computation` |
