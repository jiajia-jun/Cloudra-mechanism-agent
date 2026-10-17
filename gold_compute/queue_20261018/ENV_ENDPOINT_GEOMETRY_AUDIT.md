# 当前端点geometry mismatch只读审计

旧done→Freq阻塞已由系统接续，不能再描述为当前no-submit。当前TS频率、IRC、reactant Opt/Freq已实际执行，但几何一致性验收candidate_only；没有strict pass。env未修改run/证据、未提计算、未读应用源码。

## 文件对照（2026-10-18快照）
每行基目录为 `ts/<run>/jobs/declaration_<rev>/`，原生最终XYZ为 `reactant_opt/reactant_opt.xyz`（优化日志NAME=reactant_opt.inp绑定），保存几何为 `reactant_frequency/optimized.xyz`，同时与同目录reactant_source.xyz逐字节相同。频率输入为reactant_frequency.inp，频率日志NAME=reactant_frequency.inp。未从轨迹末帧或任意日志最后坐标手造结构。

|题/run/rev|Opt/Freq job|原子序|max原生XYZ→保存差 Å|保存→Freq输入差|
|---|---|---|---:|---:|
|IA8/ts_0001/0006|816/819|C O O H H|4.829626000235621e-7|0|
|IB9/ts_0005/0007|813/814|C C N N C H H H H H H|4.5619493005411016e-7|0|
|IB10/ts_0007/0003|808/810|O C C N N H H|4.831296199769852e-7|0|
|IA5/ts_0004/0007|815/818|C C C C H H H H H H|4.892815501644776e-7|0|
|IA1/ts_0002/0011|817/820|C C C C H H H H|4.953373299865227e-7|0|

五行原生XYZ round(6)均与保存几何**逐值完全相同**。原子序未变；频率输入坐标全部逐值等于保存几何，输入首原子整行亦出现在原生频率日志回显中。直接确认保存链6位量化；未证明validator阈值、内部取帧或具体判据实现。日志回显不是另一个独立全精度频率XYZ；NumFreq位移结构也不能当参考中心。

### SHA256索引
各行依次为 native XYZ / saved optimized.xyz（亦source） / frequency input / frequency log：
```text
IA8 e4f5311962d58b3cd2049a85d5dd6cde74756444423089b2ad2f38c64daf4df8 eec0732aae8c8bc7905c33d57fe1a31e3571af6ce3ac157a4160525240ddeb88 4e76a1e973583b00047b634cb47661c20dee6468e729b01238230559cdd9ac4a 5084bea429ce1706240343bbf6821873afab8f8042ef46e3ecee59b380935ec8
IB9 a320d6ac67a3d9503e4938e447fc323e2a44cc2af57c81dc24ed8d667fbf13b7 d9f7f36d64e58d5da2492b8dffdbb2fda8237f558e103a72c3ff558f9b7ad106 8693ece9db0f5e3af6746e1c438add9841f0f3dcde35da7c8a5d604c1dadc7d6 7f69507bf7263dbc4cec9ad972ef04d5ad65ce1192bbb17641a692563db1bf30
IB10 2fb0761dc4218af3575a3920c2964b2c972bbc50d84e9629d61c263a2ed0052a 83cb5f31af34bb656ba241a39f41cc349945ae311adbfb2fdfbdb7fdfe1f6339 777890b8b401060a4e3cac73ef627fc91f31c61c456b074ffda1088f3c784db0 5c15dc8899d8c6381cb3390216fe6f82b575aafbef789a60ab444efd38c3031d
IA5 43e98f39b4b68e7709a2f2c372cb676b5a2f0d9dd1273430aba8ee066d274644 2ef7bf66ac106b2b2ff52197d33852f3f72ecb6e6af8ff666e9ab174e07318b1 943d4efef65710fa9f8d001d3a133f89f99374234433aa3265856ae491b67716 7a2853059328210a171df98dce8da3304f7f511665f29b3f49e4ef621e201e29
IA1 b9f9d971348552e609b6a88b982c4dcd41713c394a102efb2d52d141229b03cb 094e02c96b812c271b60f3a8c3a9ea4e77bdfdae58192527bfebf5923de37f06 54f3ed0174861fbdef050e237479de3ace5af5c381a51762e6f6e4f7f937844b a6d9ff61c37f81c55be5c40456f4ed21480b3d5fb84445e1ead92730d132c578
```

IB10直接读取优化日志3633–3647行：FINAL ENERGY EVALUATION AT THE STATIONARY POINT的ANGSTROEM表为6位小数，逐行对应保存几何；原生XYZ则14位。例如O x -0.32801048312962→-0.328010。因此这组数据不支持“保存的是初始Opt帧”；它支持从打印精度坐标得到保存结构的解释。未对所有频率日志手解析中心几何，也未据此证明解析器内部取帧原因。

## 当前状态与科学问题分离
直接inspect：IA8 tc_ae72c50473fd448d rev50时819尚running，随后owner确认819完成同错；IB9 tc_e3c0477b7cc04cd8 rev74明确813/814重算后仍endpoint geometry mismatch；IB10 tc_eca58fca2cfb4503 rev47同错。IA5/IA1最新seed修复后815/818、817/820同错由owner交接并纳入上述文件实测。重复seed/Opt已不能去掉确定的6位保存行为，不建议继续盲重算。

IB10 owner另证O–N成环、非声明链状反应物；这是独立物种/路径失败，不能用精度问题抹去。IA8 strict重原子watch方向/组成不通过同样独立，不能因几何量化解释就宣布strict pass。其他题也须另外审核端点身份与IRC目标模式。

## 合法修复建议
由受权维护者对照**NAME绑定原生最终XYZ、优化日志参考、保存中心、频率输入/日志**的实际比较规则，确认是否混用打印6位与写入8位/原生14位。若确定量化触发误拒，应在受权提取/验证路径统一精度或使用带摘要原生最终XYZ导入，并保持原子序与科学身份独立验收；不要手改既有source、输入、日志、阈值或run状态。只有维护者修复后才能由原owner合法恢复所需阶段；不能将本表当成绕过mismatch的pass证据。

当前未找到owner声明参数可阻止该已发生的保存量化；多次重跑不能修解析/提取规则。下一步是维护者核具体不一致项，而非直接放宽strict或替换独立物种seed掩盖IRC连接。
