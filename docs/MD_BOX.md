# 混合溶剂建盒（`md_box`）

`md_box` 调用 Packmol 把指定的分子结构和数量装进一个三维正交周期盒里，输出初始坐标和建盒报告，方便后续接 GROMACS 或其他分子动力学软件做松弛和模拟。

使用前确保 `PATH` 里有 **Packmol ≥ 20.15.0**（[官方安装指南](https://m3g.github.io/packmol/userguide.shtml)）；如果输入是 MOL/SDF 文件，还需要安装 `cloudra[chem]` 里的 RDKit。

## 基本用法

```json
{
  "components": [
    {"structure_path": "water.sdf", "count": 100},
    {"structure_path": "ethanol.sdf", "count": 100}
  ],
  "box_lengths_angstrom": [24, 24, 24],
  "output_dir": "md/water_ethanol"
}
```

除了直接给 `box_lengths_angstrom`，也可以改填 `initial_density_g_cm3`，让程序按总质量自动算出立方盒边长。输入的 XYZ / MOL / SDF 模板单位都是 Å，每个分子当作刚体摆放（多帧 XYZ 取最后一帧）；分子间最小间距 `min_distance_angstrom` 默认 2.0 Å。想复现同一份初始排布时，把报告里的 `seed` 填回去即可。

## 输出与接 GROMACS

建盒后会在目标目录下生成：
- `box.xyz`：Extended XYZ 格式，带着周期盒向量、原子坐标和质量；
- `box.json`：记录实际分子数、名义浓度、盒尺寸、初始密度和最近分子间距（如果某个分子离自己的周期镜像太近，报告会主动提醒）。

如果要喂给 GROMACS，先用 `format_converter` 把 `box.xyz` 转成 `box.pdb`，再跑 `gmx editconf -f box.pdb -o box.gro` 就行（力场拓扑由后续建系步骤准备）。

用 MOL/SDF 建盒时，程序会拿完整 InChIKey 去对照内置液相密度参考表；如果初始密度和参考值偏差超过 20%，会在报告里标出实测参考条件提醒你，但依然正常输出盒子。

## 自己补充参考密度表

直接编辑 [md_box_densities.json](../cloudra/tools/core/md_box_densities.json) 即可：
- `pure` 按完整 InChIKey 建索引，填化学名、`density_g_cm3`、`temperature_k`、`pressure_kpa`（来源没写压力就填 `null`）和原始 `source` 链接；
- `binary` 记录二元混合物的同一温压实测点列表 `points`（按第一组分摩尔分数递增的 `[摩尔分数, 密度]`），查询时在相邻两点间线性插值。数据可取自原始文献或 [NIST ThermoML](https://www.nist.gov/mml/acmd/trc/thermoml/thermoml-archive)。
