# HL1 — 反应物预络合物构建溯源（RC_exo / RC_endo）

## 建模条件（本题面声明 = 实际模型）
- 反应：HCNO（fulminic acid, C#[N+][O-]）+ 降冰片烯 C1=CC2CCC1C2 → 异噁唑啉稠合三环产物 C1=NOC2C3CCC(C3)C12。
- 条件：**气相**、净电荷 0、单重态；无溶剂、无抗衡离子、无添加剂；未建温度/浓度（报告一律用纯电子能 ΔE）。
- 方法：Gaussian 16，B3LYP/def2SVP + EmpiricalDispersion=GD3BJ + Int(UltraFine) + SCF=Tight，4c/6144MB，priority 0。
- 规模：21 原子（C8H11NO）。

## 原子序（本 lane 工作序，与题面 atom-map 对照）
- 1–17 = 降冰片烯：**1 = 题面 C4（烯碳）、2 = C5（烯碳）、3 = C6（桥头）、4 = C7、5 = C8、6 = C9（桥头）、7 = C10（亚甲基桥）**，8–17 = H。
- 18 = C1（偶极 C）、19 = N2、20 = O3、21 = H（偶极 H，挂 C1）。
- bond_changes（题面 map 下标）：形成 [1,4]（C1–C4）与 [3,5]（O3–C5）；C4=C5 [4,5] 键级下降。

## 几何来源
1. 降冰片烯：RDKit ETKDGv3(randomSeed=20261018) 嵌入 + MMFF94 优化（[norbornene_mmff.xyz](norbornene_mmff.xyz)）。
2. 面定义：u = 单位化(C5−C4)（烯轴），n = 单位化((C5−C4)×(C6−C4))，取 **n 指向 exo 面**（C10 在 n 方向坐标 = **−0.862 Å**，即 C10 位于 endo 面一侧，故 endo 面 = −n）。
   - 实测：两个 "exo" 亚甲基 H（C7-H、C8-H，工作序 10/12 的 H）在 n = +2.210 Å、w = +1.453 Å；两个 "endo" 亚甲基 H（C7-H、C8-H，工作序 11/13 的 H）在 n = +1.468 Å；亚甲基桥 C10 的 H 在 n = −1.895 / −0.874 Å。
3. 偶极片段：理想刚性 HCNO 局部坐标（C=N 1.161、N–O 1.207、C–H 1.061、C–N–O 与 H–C–N 取 180°），整体刚性放置在面上：C(dip) 位于 C4 正上方 h 处沿面法向，分子长轴沿 u（C 端指向 C4、O 端指向 C5），再对整体做 (h, s 沿 u, woff 沿 w, th 绕 w 倾斜) 网格搜索，目标 = 两个新成键距离落在 2.80–3.20 Å 且最小分子间接触最大化（起手阈值 2.05 Å，另加 |woff| 罚项）。搜索脚本 [search_place2.py](search_place2.py)，落地脚本 [write_rc.py](write_rc.py)，参数见 [place_params.json](place_params.json)。

## 两个预络合物的实测几何（构建时，QM 前）
| 面 | d(C1–C4)/Å | d(O3–C5)/Å | 最近分子间接触 | 备注 |
|---|---|---|---|---|
| exo（−n，背向 C10） | 2.977 | 3.149 | 2.060 Å C(dip)···H(C8-exo, 工作序 13) 与 2.060 Å O(dip)···H(C7-exo, 工作序 11) | 需 woff = −0.40 Å 让开两个 exo-亚甲基 H |
| endo（+n_endo，朝 C10） | 2.952 | 3.158 | 2.057 Å C(dip)···H16(C10 上的 H) | woff = 0，s = +0.10 |

无 <2.0 Å 的原子对；两个新成键距离都在 2.8–3.2 Å 窗口内。

## 区域化学说明（为何只建一种）
降冰片烯 C4/C5 等价（分子有镜面），故 (C1→C4, O3→C5) 与 (C1→C5, O3→C4) 是同一化合物的镜像——两种区域异构体不构成独立面选择性问题。每个面各建一个取向。

## 输入与作业
- [HL1_RC_exo_optfreq.gjf](../jobs/HL1_RC_exo_optfreq.gjf) → job 1158
- [HL1_RC_endo_optfreq.gjf](../jobs/HL1_RC_endo_optfreq.gjf) → job 1159
