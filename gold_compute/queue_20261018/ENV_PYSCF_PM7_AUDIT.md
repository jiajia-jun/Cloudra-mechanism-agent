# “在PySCF里调PM7”接口核验（2026-10-18）

用户纠正后，本报告取代此前将PySCF理解成新Hamiltonian的规划；不推进CASSCF/HF/DFT替代，未进行分子计算、安装插件或修改环境。

## 关键后续：现成的PySCF回调包装器（当前结论）
本机公开API `pyscf.geomopt.as_pyscf_method` **存在且可导入**；inspect.signature精确输出 `(mol, scan_function)`。公开docstring规定 `scan_function : [mol] => (e_tot, grad)`，将回调包装为PySCF gradients scanner，可传给optimize；示例为RHF scanner经该包装器进入berny_solver.kernel。故用户“在PySCF里调PM7”有真实可行的外接设计：**PySCF通用scanner包装器 → 自定义energy/gradient回调 → ASE → MOPAC PM7**。无原生PM7对象并不阻止这种包装器调用；前文无现成接口的结论仅指无现成PM7专用实现。无需另造PySCF scanner协议，需开发/核验的是MOPAC回调。

回调应对传入的mol取 `mol.atom_coords(unit="Angstrom")`，按相同原子顺序更新ASE，电荷/电子态显式一致。返回能量Eh及梯度Eh/Bohr，ASE端换算：`E_Eh=E_eV/units.Hartree`；`grad_Eh_Bohr=-forces_eV_A*units.Bohr/units.Hartree`。实测ASE常数Hartree=27.211386024367243 eV、Bohr=0.5291772105638411 Å；梯度是力的负号，不能直接把forces塞入。能量口径必须绑定实际MOPAC/ASE解析字段，不把Hf、总能、free_energy混用。

本次只inspect.signature/getdoc与常数读取，没有构建mol、调用包装器求能或执行MOPAC。geometric/berny缺失，单回调SP/梯度检查无需优化器，真正普通几何优化仍需补依赖和科学验收。官方API入口 https://pyscf.org/pyscf_api_docs/pyscf.geomopt.html ，在线正文抓取不稳定，精确签名和契约以本机公开docstring为直接证据；未读实现源码。

协调者最新实际提交证据：IA1 job764/767、IA8 job763最终failed、attempt_count=0、last_error="Unsupported job_type: shell"。所以schema接受shell不等于执行后端支持。但协调者随后核到IA9同步shell job765/766真实成功（is_async=false、cpus=1、memory_mb=2048、省略node_id/backend；call765 tc_a447b97726194baf）。应收窄为异步路径失败；同步可行差异仍待一题最小smoke复核，不一概写shell不可。不转Bash直接算。正式TS/IRC仍仅durable，此回调不豁免后端适配与验收。

## 原生PM7最小结论
**现有环境没有已安装、可导入的PySCF PM7接口；未查得官方插件提供PM7的可靠公开承诺。** 不能把Python调用MOPAC或ASE/MOPAC计算称为“PySCF原生PM7”。这不排除开发自定义桥接，但不是当前已可验收的接口。

## 实际检查
Python `/Users/cloudrayyy/miniconda3/envs/chemai/bin/python`，PySCF2.14.0。bash执行importlib.util.find_spec，退出0：
```text
pyscf.semiempirical None
pyscf.pm7 None
pyscf.mopac None
pyscf_semiempirical None
ase.calculators.mopac ModuleSpec(.../site-packages/ase/calculators/mopac.py)
```
已装分发包清单有PySCF2.14.0、ASE3.29.0，无semiempirical/MOPAC Python桥接分发包。此证据限定已装环境，不将模块名探针提升成所有第三方插件不存在的证明。

官方PySCF组织插件 https://github.com/pyscf/semiempirical 的公开README（https://raw.githubusercontent.com/pyscf/semiempirical/master/README.md）写Semiempirical module、版本0.1.1和pip/git安装方式，未声明PM7。公开文件名清单 https://api.github.com/repos/pyscf/semiempirical/contents/pyscf/semiempirical 返回am1.py、mindo3.py、mopac_param.py、rmindo3_grad.py、umindo3_grad.py等，无PM7模块名；这提供AM1/MINDO3命名证据，不是PM7支持证据。未读取实现源码，未安装该插件；mopac_param文件名不能证明它外接MOPAC或支持PM7。GitHub PM7 issue检索0条也仅是检索结果，不作完备性证明。

## 真正存在的外接路径（不是PySCF自身）
实际import `from ase.calculators.mopac import MOPAC` 成功；公开属性打印：
```text
class ase.calculators.mopac
default_parameters {method: PM7, task: 1SCF GRADIENTS, charge: None, relscf: 0.0001}
implemented_properties [energy, forces, dipole, magmom, free_energy]
```
因此已有ASE→外部MOPAC的明确PM7参数/能量/力接口。MOPAC程序绝对路径：
`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/gold_compute/queue_20261018/results/IB9/mopac_env/bin/mopac`，23.2.5，详见[环境报告](ENV_PM7_XTB_AUDIT.md)。能量和梯度来自MOPAC，不是PySCF积分/SCF求解器；ASE forces与梯度有负号关系，并须核单位。implemented_properties没有Hessian/频率；若自行数值微分力，这是另行构建的频率流程，不能说已原生验收。MOPAC FORCE原生作业也应标MOPAC，不标PySCF Hessian。ASE默认PM7不替代脚本明确声明PM7/电荷/电子态。

Python subprocess直接启动MOPAC仅是调度。若用户坚持由PySCF工作流调用，需要专门实现并审核PM7能量/梯度scanner适配（单位、原子排序、电子态、方法/版本、收敛、异常和原生日志），目前没有已验证的PM7专用回调实现；通用scanner包装器已存在，见上方更新。不宜临时猴补PySCF Hamiltonian或拿AM1/MINDO3/PM3顶替。

## 工具门与可审计分界
有公开submit_compute_job shell能力的owner可以在普通计算范围按自身合约提交ASE/MOPAC或MOPAC作业，明示资源并由业务准入裁决；env本角色无提交工具。被拒不得Bash直接算。已存在PM7端点日志可如实保留，不因格式不被scorer读就否定科学尝试。
**正式TS/IRC仅durable：当前无已核PySCF-PM7或MOPAC durable后端；ASE/Python shell不能绕过。** [现行SOP](../../docs/TS_PROCESS_SOP.md)声明的正式写入器为ORCA/Gaussian，没有提供PySCF-PM7接口。桥接即使开发成功，也须补方法绑定、收敛/频率模式解析、双向IRC与端点身份验收；仅能计算能量/力不等于严格反应边。

已在AgentHub同步协调者、IA1与IA8：停止无关替代Hamiltonian规划。
