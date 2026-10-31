# 下载、复现与审查

Git保存正式50题、证据索引、MANIFEST哈希清单和校验脚本；原始输入、日志、几何、Hessian及来源记录保存在[公开研究数据目录](../../docs/RESEARCH_DATA_CN.md)。下载后还原到本目录，原件及`gold_compute/releases/`本地交付包已被Git忽略。

## 发布版本

版本 `20261018-d10056e7-drive1`，2026-10-18 整理，2026-11-01 开放公开读取。完整包包含 886 份整理证据、正式 50 题 JSON、逐题索引、复现说明、独立校验脚本和文件校验表，共 999 个发布文件。下载入口是在上传后登记的，不属于包内清单。

文件继承公开研究数据目录的只读权限。云端确认依据为文件名、类型、大小和权限；Drive 没有返回远端内容校验字段。以下 SHA256 用于下载后核对内容。包内字节及哈希已逐项核对，整理时回读了 12 组能垒；这不表示所有参考计算都已完整复现。

逐题缺件、来源限制与人工验收例外保留在[证据索引](README.md)及[参考状态](../queue_20261018/REFERENCE_STATUS.md)。本包提供 Gold 参考计算；P1b/P2 的 Agent 运行记录另见[研究数据入口](../../docs/RESEARCH_DATA_CN.md)。

## 1. 下载并校验

从公开[Drive入口下载](https://drive.google.com/file/d/15YDa_ycWoLUANPsDdQ1rUOiNp_-wqOs5/view?usp=drivesdk)：

`cloudra-benchmark-evidence-20261018-d10056e7-drive1.zip`

文件大小31,407,841字节，SHA256为：

```text
c7367703ca38dc3577c89ad409988294ec9594faedcee70e375e50ae4412a820
```

Linux用`sha256sum`，macOS用`shasum -a 256`核对。将以下命令的`/path/to/`替换为下载目录：

```bash
python3 -m zipfile -e /path/to/cloudra-benchmark-evidence-20261018-d10056e7-drive1.zip /tmp/cloudra-evidence
python3 /tmp/cloudra-evidence/cloudra-benchmark-evidence-20261018-d10056e7-drive1/verify.py
```

`verify.py`只用Python标准库，核对998个发布清单项、886证据、正式50题ID和已索引参考值，不执行量化计算。离线审查可从解压包根README开始。

交付包为固定快照，版本中的`d10056e7`是整理时本地快照标识，不要求从Git取得该提交。包内完整回读说明使用的已发布代码基线为`ee301060a20a55c53c0dbdaa90f043f8021e4f40`。

## 2. 还原到当前仓库

在仓库根目录运行以下Python。它按当前MANIFEST校验并只复制原件，不覆盖更新后的题库、README或程序；校验不符即停止。

```bash
python3 - <<'PYCODE'
import hashlib
import json
from pathlib import Path

bundle = Path('/tmp/cloudra-evidence/cloudra-benchmark-evidence-20261018-d10056e7-drive1')
target = Path('gold_compute/evidence')
manifest = json.loads((target / 'MANIFEST.json').read_text())
for entry in manifest['files']:
    blob = (bundle / 'gold_compute/evidence' / entry['path']).read_bytes()
    if len(blob) != entry['bytes'] or hashlib.sha256(blob).hexdigest() != entry['sha256']:
        raise SystemExit(f"Evidence mismatch: {entry['path']}")
    path = target / entry['path']
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
print(f"Restored {len(manifest['files'])} evidence files.")
PYCODE
```

逐题页面和Gold节点的`evidence_log`使用同一相对路径，还原后无需改题库。CI检查绑定路径是否登记在MANIFEST，不联网下载原件；完整日志回读按下一节另行运行。真实Benchmark依据Agent本次交付日志评分，也不会自动下载Gold原件。

本仓库保存参考证据索引，原件按下述步骤从Drive还原。这不是新的自动验收规则。先核对字节和能量，再核对结构、振动模式和真实IRC来源；回读成功不表示所有题严格科学闭环。

## 3. 核对归档和参考能垒

在仓库根目录、安装本项目Python依赖后运行：

```bash
.venv/bin/python gold_compute/evidence/audit.py
```

脚本只读文件，不提交计算。它逐文件核对MANIFEST里的长度和SHA256，逐行核对28份恢复输入与原生日志回显，核对50题目录，并用当前Benchmark解析器重算已索引的12组TS−参照能差及虚频数。NR1_E4原件缺失单独输出KNOWN GAP，不以报告中数值冒充原生日志。老题其余数值没有在本脚本中逐边回算。

纯电子能差：`(E_TS − E_稳定参照) × 627.5094740631 kcal/mol`。同一物种的已声明构象连接按用户确认的稳定中间体口径；构象转换用自身起点。不同立体底物与独立通道接触体分开。IB9参考两软虚频是显式人工例外，不能推广为通用豁免。

某些ORCA 6.1外部势日志会触发cclib的解析提示；当前Benchmark解析器有原生文本回退。脚本退出码、逐项读数与原生正常终止记录一起查看；不可把cclib提示、脚本退出0或报告摘要替代科学判断。

## 4. 找到一次计算的完整输入

每题README列出日志、对应输入、必要的外部文件及限定。MANIFEST的sources保留原目录/作业号；同SHA别名指向同一保留文件。原endpoint_source.json中的绝对路径/哈希不改写，按该映射追溯实际IRC、末帧和后续作业。

`.recovered.inp`逐行提取对应ORCA日志的INPUT FILE编号行，不含展示编号。MANIFEST记录派生来源和原日志行号；这类输入不是从优化终态反推。最终链需要读取的原始起始XYZ也保留，不能用终态XYZ或另一个Hessian代替。

## 5. 在独立工作目录重跑

原文件保持只读，把所需输入与依赖复制到独立工作目录。只在工作副本调整失效的绝对文件路径（Gaussian `%chk`输出路径、ORCA `Hess_Filename`/`xyzfile`读取路径）和适合本机的资源配置；保留方法、基组、色散、溶剂、电荷、多重度、坐标、约束及TS/IRC参数。逐题外部依赖见题目README，不能只按相同文件名猜测驻点。

ORCA示意：将某题所需原始输入复制为run.inp、依赖按表重定位后，以实际ORCA二进制绝对路径启动：

```bash
/path/to/orca run.inp > rerun.out
```

Gaussian示意：将该阶段原始输入复制为run.gjf并设置可写的工作副本chk路径后运行：

```bash
g16 < run.gjf > rerun.log
```

现代Gaussian链使用原日志所记的Gaussian16；IB9为ORCA6.1.1外接GFN2-xTB6.7.1。旧ORCA任务的确切版本和方法逐项看原生日志/输入，不能统一替换为xTB或新版本。运行ORCA外部xTB任务时须能找到日志中声明的xTB程序。

顺序是：参考/端点优化与频率、TS优化与频率、由该TS的Hessian开展双向IRC、由真实两端末帧分别优化与频率。原始文件的独立种子若没有真实IRC来源，不因重放能垒成功就自动补成方向证明。

HA1、NU6各两条IRC原始Hessian缺失：先复算同一步的TS.recovered.inp（其中包含Freq）生成同级别TS Hessian，再在IRC工作副本引用新产物。这是重新生成依赖，不声称恢复了原Hessian字节。

## 6. 人工审查顺序

1. 对照正式题目确认结构身份、原子映射、电荷/多重度、理论级别及参照体系。
2. 读优化是否收敛和原生正常终止；极小值0虚频、TS1虚频，并看TS振动是否沿目标反应。
3. 对照实际IRC与endpoint_source；从同一TS真实双向末帧到身份正确的零虚频端点才构成方向证明。稳定能量分母另行核对，不强行把它写成IRC直接端点。
4. 用原生能量重算能差；区分独立种子、构象辅助剖面、人工采信和成功闭环。缺件与当前科学限定见每题README，不用旧报告pending或旧题库值覆盖正式定义。

归档只清除不再支撑当前参考的试错。仍影响结论的失败证据、缺件和人工验收说明必须保留。
