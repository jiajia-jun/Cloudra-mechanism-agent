# IA8自身IRC端点strict行为有限审计

只读[实际请求/返回](results/IA8/endpoint_strict_review/strict_own_endpoints.json)，call tc_8b3a7df380064bda；不新增QM/strict、不读应用源码、不移动改写证据或更改watch/阈值。

本次freq835/IRC836，确实使用836自身B→841反应物、F→840产物OptFreq的原生末XYZ reference，不再使用早先explore独立端点。因此早前独立reference结果不能外推到本次。owner核原子序C/O/O/H/H未置换，两端正常收敛0虚频，最低503.56/1020.46 cm−1；[来源/配对/哈希与距离表](results/IA8/endpoint_strict_review/endpoint_comparison.json)给质量加权Kabsch RMSD B→R=0.004634653442929Å、F→P=0.001907459848809Å，max原子位移0.01848737574/0.00924488528Å。该数值为owner交接，env不重复计算；接近不自动等于工具验收pass。

返回checks只有：一虚频−950.47；watch [[0,2],[0,1]] relative displacement .351/.368，max .368低于.629阈值（0.5×global1.259，dominant pair(3,4)）。verification_status=fail，imag_mode_aligned=false，IRC end_a/end_b path均空，无端点匹配、距离或方向检验check。**不能声称本次实际完成了endpoint-match优先验收；输出与早期mode拦截相符，但不能证明内部永久执行顺序或未公开步骤。该fail不能被解释成端点连接错误。**

IA8 owner重新核现行完整公开合同：strict要求一虚频、双向有效IRC外端、TS几何及两reference，检查partial端点是否在TS与匹配reference之间，返回direction-consistency pass/fail/inconclusive；reactant/product_path接受XYZ。没有“endpoint匹配优先”承诺或匹配成功覆盖mode失败的控制字段。env自身get_tool_docs(ts_guess)回执tc_8f6e10be1d7843c3 unavailable，因此合同依据明确归属owner现行原文交接，不假称env独立读取。

当前精确能力缺口：本次公开输出未提供端点优先审查结果，合同未提供独立endpoint-match入口/优先控制。需维护者明确如何受权得到用户要求的独立配对/方向审查及它与模式判据的关系，不能由Agent删watch、改阈值、追加日志、重复试参或擅自pass。模式阈值不通过和端点配对证据分列；原生自身端点已优化且同序的事实应保留，不以mode fail否定它。
