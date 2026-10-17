# IMP PM7 / xTB 环境与 TS/IRC 能力查验（2026-10-18）

本查验未做任何分子计算，未安装或改动软件；不参与 IA1/IA8/IA9/IB9 物理计算。

## 实测与边界
- 主机 macOS 26.3.2 arm64，18 CPU，内存 51539607552 bytes（48 GiB）。sysctl -n hw.ncpu hw.memsize；uname -a；sw_vers。建议小分子单作业 1–4 核、避免并行数值 Hessian 超售；这不是计时预测。
- which -a mopac MOPAC xtb crest orca gaussian g16 g09 psi4 nwchem terachem：只发现 xTB、CREST、ORCA；全命令退出 1 因存在未找到程序，不能据此说所有引擎不可用。
- /Users/cloudrayyy/opt/orca_6_1_1/xtb --version：6.7.1 (edcfbbe)，编译日期 2026-06-10，normal termination；另 /Users/cloudrayyy/miniconda3/envs/chemai/bin/xtb。xtb --help 实列 --opt、--hess（numerical）、--ohess、--path（metadynamics）。path 不是 IRC，更不是 TS 证明。
- /Users/cloudrayyy/opt/orca_6_1_1/orca 启动 banner：Program Version 6.1.1 - RELEASE，libXC 7.0.0。注意 --version 被当输入文件，末尾报 Cannot open input file，不能将这个诊断误记为成功分子计算。
- PM7 不在本机 ORCA 接受的方法中：专家已有原生日志 [t_pm7.out](results/IB9/probe_pm7/t_pm7.out) 第179–181行 INPUT ERROR / PM7。不得以 PM3、PM6 或 GFN2 替代 PM7。
- 发现同期 IB9 专家安装的 MOPAC 独立环境（不在 PATH）：results/IB9/mopac_env/bin/mopac，file 确认 Mach-O arm64；[conda 元数据](results/IB9/mopac_env/conda-meta/mopac-23.2.5-h927232e_0.json) version 23.2.5，build h927232e_0，Apache-2.0，osx-arm64，包 sha256 ea6cdd471ba989f2eacd715ce6193c2fad2d687d563614c2f255634e89c6dc84。[安装日志](results/IB9/mopac_install.log) transaction done。无参启动等待输入超时，尚不能由此确认 PM7/TS/FORCE/IRC 全功能正常。授权证据为包元数据，不是旧知识库“仅学术免费”说法。
- 无本机 Gaussian 可执行证据；ORCA 实际许可证/机构使用授权文件本次未找到，安装存在和已正常计算并不等于已审核使用许可。xTB 许可证也未在本次包证据中核实，不推定商业许可。

## durable 与原生证据
[现行 SOP](../../docs/TS_PROCESS_SOP.md) 第12、25、29、60、76–90行是项目文档，不是源码：native engine=xtb 只支持显式 GFN2-xTB 的种子优化、path、柔性扫描；正式阶段各自声明 ORCA/Gaussian calculation，basis_set 空字符串必须明确。正式 xTB 应通过 ORCA GFN2-XTB + 数值频率；已有 [rect_optfreq.inp](results/IA1/rect_optfreq.inp) 与 [原生日志](results/IA1/.cloudra/calc-731.out.log) 是专家提供的端点先例，不代表本次完成 TS/IRC。

手动 TS/IRC 提交暂时关闭，不能经 bash 绕过；必须有 producer 角色的 ts_prepare/resume durable 链。本 env 角色工具目录仅 ts_inspect，没有 qm_input_writer、submit_compute_job、ts_prepare/resume；get_tool_docs 请求前两者返回 Unknown or unavailable。因此只能确认文档选择能力，不能在本角色进行实际准入或 TS/IRC smoke test。原生 xtb CLI 可做 Opt/Hess，但不能把它的 path 归类为 IRC。ORCA xTB 的 OptTS/NumFreq/IRC 全链能否真正成功，仍需专家 durable 作业的正常结束原生日志，不以关键词可写作成功保证。

PM7 durable 路径当前缺口：没有已公开的 MOPAC writer/submission/parser 后端；ORCA PM7 已拒绝；本机无 Gaussian。即使 MOPAC PM7 原生日志可科学审计，TaskSpec 的 ORCA/Gaussian 格式限制也不自动接受它，须协调者明确证据接纳规则或提供授权 Gaussian 节点。不能伪装 MOPAC 日志为 ORCA。

严格门槛：TS 优化正常结束且收敛；同方法频率恰一虚频并审核目标模式；两向 IRC 有真实外帧；两侧无约束 Opt/Freq 达到身份匹配的零虚频极小点；保留输入/原生日志/方法、原子映射和摘要；只在同批同方法下相减。SOP 允许短程 partial IRC + 两端再优化，但证据不足只能 candidate_only。--uhf 0 只规定电子数差，不能声明开壳单重态；native 接口会 electronic_state_backend_unsupported。

## IA5 / IA7 / IB10 规划
1. IA5 最值得先试：闭壳小分子、模式可检验。使用旧 L1 几何仅作初猜，同级重新优化端点；明确反旋二面角和虚频方向；先 Hessian 指数再 IRC。若反旋驻点为二阶鞍点/脊线则严格边失败，不能换顺旋或引用35.17。GFN2/ORCA durable 是当前最接近可执行路径，PM7 待后端与格式解决。
2. IA7：Z 起点、C1–C6 成键、p-苯炔目标开壳单重态及产物 reaction_energy。先电子态后 TS；当前 native xTB 开壳单重态门槛明确阻塞，闭壳收敛不能充作目标态。PM7 即使能执行也须专门的态表示与诊断，不能承诺严格反应边。
3. IB10：分步 N2 脱离到单重态甲酰卡宾，再 H6:C4→C3 迁移。先核卡宾电子态及碎片端点；每步分别验证，不可用直接协同旁路补题。当前原生 xTB 不能证明目标低单重态，PM7 后端亦未验收；优先级低于 IA5。不得恢复旧闭壳4.34。

## 后续协调澄清（以此为当前状态）
协调者确认 MOPAC 23.2.5 已可执行；env 未掌握成功 PM7 输入/脚本路径，不把安装成功等同于分子作业成功。协调者公开合约核查指出：其他 specialist 的 submit_compute_job 可有 job_type="shell"，可按各自实际合约尝试普通 PM7 Opt/FORCE、显式资源，由业务结果裁决。env 自身缺提交工具不能推广为所有专家无通道；被拒不可转 Bash 算。正式 PM7 TS/IRC 仍缺已验证 durable 后端，不能 shell 绕过。IA5/IA8/IA9 多个 ORCA external-MLIP TS opt 已收敛但 waiting/refine 未启动频率，协调者认定共性推进障碍，不能写物理不可达。方法风险亦只是待检验假说，不提前设置 accessible=false。

## 外部核查及失败
web search 工具两次失败 deepseek_api_key not configured（非科学证据）；未从记忆宣称当前版本。官方 xTB 页面 GET 可达 https://xtb-docs.readthedocs.io/en/latest/spgfn.html ，标题 Spin-polarization；SOP 同时引用该来源。https://openmopac.net/manual/IRC.html 返回404，正确站点导航为 /Manual，不以404证实不支持 IRC。ORCA 官方页面与 GitHub 抓取未取得可用正文，故软件能力以 CLI、包元数据、项目 SOP 及实际原生日志为准。

诊断副作用：无参 MOPAC 探针超时后发现等待进程 PID56160（PPID1）；清理尝试被 bash 安全闸拒绝，未执行。已告知协调者；请由进程所有者核对后清理，勿影响专家分子作业。
