# PySCF 环境能力审计（2026-10-18）

用户转向“没有pm7试试pyscf”。仅环境/import/API核查，无分子构建、能量、梯度或频率计算；未安装/修改任何软件。先读 [PROCESS](../../PROCESS.md) 与 [前轮审计](ENV_PM7_XTB_AUDIT.md)。PySCF是程序而非Hamiltonian，方法、基组、活性空间、电子态仍需专家显式决定。

## 实际可执行环境
绝对Python：`/Users/cloudrayyy/miniconda3/envs/chemai/bin/python`。
实测Python3.11.16、PySCF2.14.0、NumPy2.4.6、SciPy1.17.1、h5py3.16.0；PySCF加载路径 `/Users/cloudrayyy/miniconda3/envs/chemai/lib/python3.11/site-packages/pyscf/__init__.py`。importlib.metadata 的许可证字段 Apache-2.0。无需新建或重复下载PySCF环境。

检查命令（bash，退出0）：
```sh
/Users/cloudrayyy/miniconda3/envs/chemai/bin/python -c 'import sys,pyscf,numpy,scipy; print(sys.executable,sys.version); print(pyscf.__version__,pyscf.__file__); print(numpy.__version__,scipy.__version__); from pyscf import scf,dft,mcscf,grad,hessian; print("imports scf dft mcscf grad hessian OK"); print(pyscf.lib.num_threads())'
```
输出版本如上，imports OK，默认线程18。另一import-only检查以 importlib.import_module 逐个核对：
- `pyscf.grad.rhf`、`pyscf.grad.rks`、`pyscf.grad.casscf` 均成功；CASSCF类公开属性 `nuc_grad_method` 存在。
- `pyscf.hessian.rhf`、`pyscf.hessian.rks`、`pyscf.hessian.thermo` 均成功；thermo.harmonic_analysis可调用。支持RHF/RKS Hessian/谐振分析的API存在，不代表任意泛函、电子态和体系均验收。
- `pyscf.hessian.casscf` 缺失。**不能承诺CASSCF解析Hessian/频率已支持。**可规划对解析梯度的中心数值微分，但属于待实现/核验的计算方案，必须验证位移步长、单位、平移转动投影、每点态/轨道跟踪与收敛，不把梯度接口当频率成功。
- `importlib.util.find_spec("geometric")` 和 `find_spec("berny")` 都是None：现环境缺这些外部几何优化器。本次未安装，SP无需因此阻塞。

## 能力分界与提交
RHF/DFT/CASSCF基础模块及相关梯度API可导入；小分子SP可由有授权工具的owner写明方法/基组后尝试。CASSCF(4,4)/cc-pVDZ是IA1协调任务指定方案，不是默认推荐，更不保证自动挑中正确四个π轨道；需保存轨道成分、占据、根/自旋选择和收敛日志。

协调者核查公开 submit_compute_job 合约可有 job_type="shell"：有此能力的专家先读取自身实际合约，提交Python脚本并显式CPU/内存，按业务返回判断准入。env自身目录不含该工具，未提交shell或分子作业；不能从env缺工具推断所有owner无shell。被拒不得Bash直接计算。输入几何应读已有受信XYZ/MOL并保留原子映射，不手打新几何。保留stdout/stderr、PySCF原生输出、输入脚本和环境/电子态，不伪装ORCA日志；TaskSpec格式/scorer兼容另审。

**正式TS/IRC：无已核PySCF durable后端。** [TS SOP](../../docs/TS_PROCESS_SOP.md) 第25行将正式写入器限定为已有ORCA/Gaussian，原生GFN2用于种子/path/scan；文档未声明PySCF适配。本角色无ts_prepare工具，不能以实际prepare探测。因此准确结论是“当前公开文档与本角色能力未提供PySCF TS/IRC适配”，不是PySCF数学上不能用于TS/IRC。不得通过shell/Bash另跑正式TS或IRC绕过durable；需工程适配/准入后另行验收。安装geomeTRIC也不会自动补齐durable作业、方法绑定、日志解析与端点科学门。

## 资源
主机18CPU/48GiB；默认PySCF线程18易与并行owner超售。建议每小分子普通作业先1–4核，提交CPU与OMP_NUM_THREADS、MKL_NUM_THREADS、OPENBLAS_NUM_THREADS及脚本pyscf.lib.num_threads保持一致；max_memory以MB明确设置并留Python/积分/外部进程余量，它不是硬内存上限。CASSCF成本依轨道数/活性空间变化，不从8原子保证耗时。频率若数值微分，逐位移收敛和态跟踪比并发堆核更重要。

## 文档出处与限制
官方文档入口 https://pyscf.org/user/grad.html 与 https://pyscf.org/user/geomopt.html 已GET/HEAD核查，但本次抓取未取得可用于引用的能力正文，不夸称逐条官方文档验收。具体本机能力依据实际import和公开API存在性检查；未读取应用源码或包实现。项目后端限制依据上述TS SOP。先前网络search缺API key，外部资料核查不取代本机版本证据。

已向IA1 owner提供上述路径与结果；同步协调者及IA8。后续若需普通端点优化，由协调者决定是否新建隔离环境补装优化器；本任务无需为SP修改共享chemai环境。
