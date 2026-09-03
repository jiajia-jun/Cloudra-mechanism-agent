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

- OMol25 权重（仓库内）：`ideapool/mlp_benchmark/models/md_omol25/2025_levine_omol25/2025_levine_omol25.md`
  （232557 字节；此 .md 后缀实为 MACE 模型二进制）。
- ORCA 探针实际使用的本地模型：
  `/Users/cloudrayyy/opt/mace-omol25/MACE-omol-0-extra-large-1024.model`

## 7. 关键文件索引

| 文件 | 说明 |
| :--- | :--- |
| `cloudra/skills/dft-calculation/references/mlip-gaussian-external.md` | MLIP external 引擎说明（公用 skill）：Gaussian g16-mlips 通用段 + ORCA `ExtOpt` 路线（qm_input_writer `engine="orca"` 生成；ProgExt/权重路径为部署占位，本机具体值见本文档 §3.3/§6；运行时环境变量已由 `calculator.sh` orca 分支自动注入） |
| `paper/reference_answer_task_P1.md` | P1 能垒标定任务单（具体题号列表在文档后段） |
| `paper/reference_calc_plan.md` | 能垒标定宏观分工计划 |
| `ideapool/tasks/<tier>/<task_id>.json` | 题目定义；回填目标字段 `gold.reference_computation` |
