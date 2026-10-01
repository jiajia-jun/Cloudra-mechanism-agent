"""H/I/J 族登记：笼状价异构（H7 pagodane / H8 propellane）+ 反常键与基态之争
（I2 硫代臭氧 / I8 磷宾）+ 重排小势能面（J6 甲氮烯 / J7 二硅烯）。

H7 为键重组无法从 SMILES 级映射差集推导的笼状价异构（显式 no_mapping）；
H7/H8/I8/J6/J7 是定稿风险登记的 6 条灰色地带题（均未登记进本表）。
"""

TASKS = {
    # pagodane ⇌ dodecahedrane：2σ→2σ 二电子价异构，TS 必经 biradicaloid 区；
    # 硫代臭氧 S3：SCF/CISD 会把基态误判为环状 D3h，只有 CASSCF/MR-CISD 给对开式 C2v
}
