# ORCA NumFreq 原生坐标输出：官方依据与未知项

## 目的
配合[STRICT_PARSER_AUDIT.md](STRICT_PARSER_AUDIT.md)所记 missing TS geometry：不改完成日志、不造XYZ或bundle，不改变Hamiltonian，也不追加Opt/TS/IRC任务；仅允许owner通过正式durable频率声明试验原生输出完整性。

## 已核实官方参数
ORCA 6.1官方手册[§2.4 Control of Output](https://www.faccts.de/docs/orca/6.1/manual/contents/essentialelements/output.html)，表2.6列 `P_Cartesian`，描述为 **“Print the cartesian coordinates”**。正文说明 `%output` 的 `Print[<option>]` 可修改PrintLevel默认值，数值1开启。最小候选block：

```text
%output
  Print[P_Cartesian] 1
end
```

保持原方法、NumFreq、几何与其余设置，仅在工具公开契约支持时声明此输出block；若契约无该字段，应报告适配缺口，不手改生成输入/证据。无需提高PrintLevel。

## 明确保留unknown
同页表2.7的mini默认已经包含P_Cartesian=1，因此显式设置是否能让external-GFN2-xTB单独NumFreq真正调用坐标打印分支，**尚未证实**。官方通用定义足以支持一次受控输出实验，但不是成功保证，也不证明旧任务设置错误。若新原生日志仍无Cartesian表，应记录实际结果并交维护者支持hess/input TS中心解析，不以重复相同QM代替修复。

同页表2.8对 `XYZFILE` 仅说 **“Produce an XYZ coordinate file”**：这不保证日志有Cartesian表，更不保证strict会消费该sidecar，因此不将XYZFILE当已证实替代方案。

## 研究操作
仅只读官方网页与strict审计，已把精确block/URL及unknown同步IA1 owner和协调者；未提交计算或修改原生日志。
