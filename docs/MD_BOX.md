# 混合溶剂建盒

`md_box` 用 Packmol 将明确给出的分子结构和数量放入三维正交周期盒。它交付初始坐标、周期盒与建盒记录。下游计算按所选方法准备参数并松弛结构。

在 Cloudra 运行环境的 `PATH` 中提供 Packmol 20.15.0 或更新版本。MOL/SDF 还需要 `cloudra[chem]` 中的 RDKit。[Packmol 安装与使用](https://m3g.github.io/packmol/userguide.shtml)

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

也可以用 `initial_density_g_cm3` 代替 `box_lengths_angstrom`，让程序根据总质量确定立方盒的边长。XYZ、MOL 和 SDF 模板使用 Å，提供已准备好的三维构型和参与建盒的全部原子。多帧 XYZ 使用最后一帧。每个模板的内部坐标作为一个刚体一起摆放。`min_distance_angstrom` 默认 2.0 Å，用于不同拷贝间的周期近接约束。需要复现初始排布时，复用报告中的 `seed` 和后端版本。

新目录内的 `box.xyz` 使用 Extended XYZ 保存周期盒、坐标与质量。`box.json` 记录实际数量、名义浓度、盒尺寸、初始密度和不同拷贝间实测的最近距离。单拷贝时该距离为 `null`。任一拷贝离自身周期镜像小于 `min_distance_angstrom` 时，报告会给出提示。

密度检查用 MOL/SDF 的完整 InChIKey 匹配液相参考数据。XYZ 也可以建盒和计算密度，结果会注明是否有可用的化学身份和参照。相对适用参考密度偏差达到 20% 时，报告给出实算值、参照值及其测量条件，仍然交付盒子。参照温压随数据记录提供，用户可用它核对自己的研究条件。

## 补充密度参考数据

编辑 [md_box_densities.json](../cloudra/tools/core/md_box_densities.json) 即可增加化合物或二元混合物。

- `pure` 以完整 InChIKey 为键。每条记录写化学名、`density_g_cm3`、`temperature_k`、`pressure_kpa` 与原始 `source` 链接。来源未报告明确压力时用 `null`。
- `binary` 为每对组分保留一组参考条件。`components` 按顺序列出两个 InChIKey。`points` 是按第一组分摩尔分数递增的 `[摩尔分数, 密度]` 实测点。查询根据盒中的实际摩尔分数在相邻数据点之间插值。各点应对应同一温压下的同一液相。可从原始论文或 ThermoML 的论文级记录取数。 [NIST ThermoML](https://www.nist.gov/mml/acmd/trc/thermoml/thermoml-archive)
