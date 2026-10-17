# strict missing TS geometry 只读核查

## IB9可复现输入与结果
完整[原样请求/返回](results/IB9/independent_endpoints/STRICT_FULL_RECORD.json)，只读复现tc_aa51e9efa8f64325（原调用tc_1764b3279cb64414）：engine=orca，mode=verify，strict=true，watch_pairs=[[0,4],[1,2]]，freq_log为[794](../../ts/ts_0005/jobs/declaration_0006/frequency/.cloudra/calc-794.out.log)，irc_log为[798](../../ts/ts_0005/jobs/declaration_0006/irc/.cloudra/calc-798.out.log)，端点为独立普通F821/B822末XYZ。输出n_imag=1、-367.39 cm−1、imag_mode_aligned=true、两IRC末端成功提取，但Neither frequency log nor IRC provides a usable TS geometry，verification_status=inconclusive。提示重优化端点不能补缺失TS中心，不能当成重新跑QM的依据。

## 直接文件证据
- 794日志NAME=frequency.inp（第215行）；grep无CARTESIAN COORDINATES表。日志sha256 dacf14b165b8cdedff3ea964a02c541bd0b636891d738f530fa4f8d27f35c2df。
- [原生频率目录](../../ts/ts_0005/jobs/declaration_0006/frequency/)存在frequency.inp、frequency.hess、optimized.xyz、engrad/gbw/property文件；**不存在frequency.xyz**。日志在该目录的.cloudra下，不和sidecar同层。
- [frequency.hess](../../ts/ts_0005/jobs/declaration_0006/frequency/frequency.hess) sha256 24d7b5bc5b5345a38e6ac2ad5fb7efc7f86f86eed459e7f928e135cdbf0c8f90，原生$atoms从537行开始、11原子，顺序C C N N C H H H H H H，含质量与三维坐标；不是没有任何中心几何资料。此段的单位/读取仍须使用受支持ORCA解析接口，不将它直接冒充XYZ。
- [frequency.inp](../../ts/ts_0005/jobs/declaration_0006/frequency/frequency.inp) sha256 14d5b7680b3d848855c1b3e4fb11a7bbfcac5b07c6dae2e7d0c7f1640ffb831e；[optimized.xyz](../../ts/ts_0005/jobs/declaration_0006/frequency/optimized.xyz) sha256 07c1e8b757ca80fcf8fe6cc98fb83bfc9f11e33ddd709ea3a3af9ac56a0dccb1，11原子中心坐标已在保存输入中，不是轨迹末帧。
- 798日志sha256 a7d2a66bdf5fc6f3a7fbb50fe005da92d0eb4ea67d8fb7d27055697dc7318ca9。其父原生目录含irc_IRC_F/B.xyz及F/B/Full_trj.xyz；strict返回明确已恢复两个IRC外端。因此不能泛称.cloudra导致所有sidecar不可见。

## 公开合同边界
IB9 owner已读取完整ts_guess公开合约，确认strict仅有freq_log/irc_log/端点reference，无独立TS xyz字段；可由freq或IRC恢复TS几何，ORCA末端sidecar/trajectory可用于IRC外端，但**未公开NAME到父目录xyz或.hess/$atoms的具体TS中心搜索规则**。env自身目录不能获取ts_guess/log_parser/format_converter合约（Unknown or unavailable），未读取应用实现。现行TS SOP有原生日志与sidecar保留要求，没有可据以保证重排文件后strict接纳的规则。

因此当前无法确认是.cloudra路径邻接、缺frequency.xyz命名、未支持.hess中心，或其它解析路径造成；**未证明具体根因**。可以确定：原生中心资料存在，strict未消费成功；这属于精确解析能力缺口，不是靠再做相同QM解决。

## bundle与维护建议
目前无足够公开合同依据保证将日志/sidecar原字节复制到同层或重命名能解决，故**未移动、复制或改写文件，也不提供猜测性bundle作为合法pass方案**。需维护者明确并支持TS中心解析规则：以日志NAME绑定原生input/hess或受信XYZ，校验原子数/顺序/单位与频率模式一致，保来源/hash；若支持bundle，公开所需文件名、相对路径、不可变原字节约束后由owner依合同使用。不得手造frequency.xyz、追加Cartesian表或修改日志来骗过解析；也不能用IRC末端替代TS中心。

IA1 owner另报[strict_original_paths.json](results/IA1/strict_original_paths.json) tc_8b6d2b548ee34c9a：793/797有一虚频、aligned、双向IRC收敛及独立823/824零虚频端点，但同missing TS geometry；作为跨题复现交接，env本轮未重复解析该文件。不重跑QM治parser。IB9 B822两个软虚频独立保留，即使修复TS几何解析也不能自动认定整边合格。
