---
key: t51093
title: ��matplotlib��gnuplot��VMD���彥��ɫ���
url: http://bbs.keinsci.com/thread-51093-1-1.html
domain: 可视化与制图
source: keinsci
year: 2025
cards: 33
---

# ��matplotlib��gnuplot��VMD���彥��ɫ��� — 知识卡片

## 1. VMD 1.9.3 渐变色机制

VMD 1.9.3 版本定义渐变色色标需 1057 个颜色，其中索引 0-32 为基础色，索引 33-1056 共 1024 个颜色用于定义渐变的起始、结束及中间色。每个颜色的 RGB 值范围为 0 至 1，通过 `Graphics - Colors` 菜单或 `colorinfo`、`color` 指令进行设置与修改。

---

## 2. VMD 常用自定义配色脚本

为模仿 GaussView 元素配色，可使用 `gview_color.tcl` 修改索引 101-211 的颜色；为模仿 Jmol 元素配色，可使用 `JmolColor.tcl` 修改索引 101-195 的颜色；为模仿 PyMOL 的 rainbow 配色绘制二级结构，可使用 `pymol_rainbow.tcl`（即 `rainbow_v2.tcl`）修改渐变色。

---

## 3. VMD 配色模式局限性

VMD 内置的 RGB 配色模式为加权线性平均，无法像 PyMOL 的 HSV 模式那样保持色相或饱和度恒定。在绘制 RDG 等图时，这种差异会导致 VMD 生成的渐变色在视觉效果上不如 PyMOL 或经过特殊调整的 HSV 模式自然。

---

## 4. 外部工具生成 VMD 渐变色脚本

使用 `matplotlib` 或 `gnuplot` 可生成 VMD 可用的渐变色脚本。生成的文件包含同名的 `.png`（预览）和 `.vmd`（脚本）文件，Windows 系统下编写的脚本在 Linux 运行需使用 `chmod` 赋权并用 `sed -i "s/\r$//"` 修改换行符。

---

## 5. Matplotlib 生成渐变色基础用法

在安装了 `matplotlib` 的 Python 环境中，可通过 `mpl.colormaps.get_cmap(name)` 获取名为 "rainbow" 等的渐变色对象。执行 `python make_palette.py` 后会生成包含 1024 个离散 RGB 值的 `rainbow.vmd` 文件和预览图 `rainbow.png`。

---

## 6. Matplotlib 旧版 API 警告

Matplotlib 3.7 版本起 `cm.get_cmap(name)` 方法被弃用，推荐使用 `matplotlib.colormaps[name]` 或 `matplotlib.colormaps.get_cmap()` 代替。新写法应避免使用已弃用的 API 以保证兼容性。

---

## 7. Matplotlib 插值生成平滑渐变色

为解决 VMD 颜色分级导致的色带不连续问题，可使用 `LinearSegmentedColormap.from_list()` 对原始颜色表进行自定义线性插值。该方法通过指定颜色列表和灰度值（默认均匀分布）生成指定数量（`N=cnum`）的平滑渐变色。

---

## 8. Matplotlib 自定义数学函数渐变色

使用 `ListedColormap` 配合 `numpy` 可直接生成基于数学公式的自定义渐变色。例如利用 `np.column_stack` 组合由 `np.abs(2*cgry-0.5)` 等公式计算出的 RGB 通道数组，可精确控制颜色变化规律。

---

## 9. Matplotlib 渐变色反转与扩展

Matplotlib 生成的渐变色对象可通过 `cmap.reversed()` 或添加 `_r` 后缀进行反转。此外，安装 `palettable` 库（如 `pt.cartocolors.sequential.Purp_7.mpl_colormap`）可引入更多专业的配色方案供 VMD 使用。

---

## 10. Gnuplot 生成渐变色参数设置

Gnuplot 通过 `set palette` 命令定义渐变色，支持 `defined`（灰度节点及颜色）、`rgbformulae`（公式编号）、`cubehelix`、`viridis` 等多种模式。不同模式（如 RGB 与 HSV）对参数值的解析不同，使用 `show palette rgbformulae` 可查看当前编号对应的公式。

---

## 11. Gnuplot 脚本执行与输出

运行 `gnuplot make_palette.gp` 会生成 `rainbow.png` 和包含 1024 个 RGB 值的 `rainbow.vmd` 文件，并自动删除临时的 `.tmp` 文件。Gnuplot 通过 `test palette` 命令生成的 RGB 曲线与亮度图可供参考，且其内部变量 `$PALETTE` 仅存储 256 种不同 RGB 值。

---

## 12. VMD 应用渐变色脚本步骤

将生成的 `.vmd` 脚本放入 VMD 目录，在 VMD 文本窗口执行 `source rainbow.vmd` 即可应用渐变色。若要永久生效，可将该 `source` 命令添加到启动配置文件 `.vmdrc` 中。

---

## 13. Turbo 渐变色绘制弱相互作用图

使用 Multiwfn 绘制弱相互作用（如 Reduced Density Gradient, sign(lambda2)rho）时，可将 `ESPiso.vmd` 中的默认配色脚本替换为基于 matplotlib `turbo` 配色生成的 `.vmd` 文件。通过设置映射范围（如 -0.06 到 0.06 a.u.），可在 VMD 中获得视觉效果更丰富的等值面图。

---

## 14. IRI 分析中的 Gnuplot 渐变色设置

绘制 IRI（Interaction Region Indicator）散点图时，可通过修改 `IRIscatter.gnu` 中的 `set palette` 命令定义特定颜色的渐变。例如，使用 `set palette model HSV defined (...)` 可以在 HSV 模式下定义蓝-绿-红渐变，这比 RGB 模式更能体现 IRI 值的物理意义。

---

## 15. VMD 中应用 HSV 模式渐变色

将 Gnuplot 生成的 HSV 模式渐变色脚本（如 `hsv-bgr.vmd`）加载到 VMD 时，需在 `IRIfill.vmd` 中设置 `color scale method BGR` 和 `color scale midpoint 0.666`。这种设置能复现类似 PyMOL 的渲染效果，使红蓝渐变在视觉过渡上更为自然。

---

## 16. Matplotlib 自定义渐变色映射方法

Matplotlib 可通过 `LinearSegmentedColormap` 构建渐变色，亦支持直接使用原始 RGB 颜色模式。Gnuplot 与 Matplotlib 使用的 HSV 颜色模式在渐变色处理上存在微小差异。为了复刻 Gnuplot 的渐变效果，需要在 HSV 空间对颜色节点进行特定偏移，例如 -0.04 和 0.02。

---

## 17. Matplotlib 颜色模式转换与插值代码逻辑

RGB 与 HSV 颜色模式可通过 `rgb_to_hsv()` 和 `hsv_to_rgb()` 函数进行转换。在代码中，首先定义 RGB 颜色数组 `colors_rgb` 和节点 `nodes`。随后将 RGB 转换为 HSV，对节点进行归一化处理，并利用 `np.interp` 在 HSV 空间进行线性插值以生成完整色板。最后将插值结果转回 RGB 空间，通过 `co.ListedColormap` 生成名为 "hsv-bgr" 的色图。

---

## 18. Python 代码中的关键参数与变量

代码片段中定义了颜色范围的最小值 `cmin = 33` 和最大值 `cmax = 1057`。这两个数值对应于 VMD 中 `colorinfo num` 和 `colorinfo max` 的参数。颜色数量 `cnum` 通过 `cmax - cmin` 计算得出，用于生成线性分布的灰度值 `cgry`。

---

## 19. 外部颜色表资源获取与应用

NCL Graphics: Color Table Gallery 提供了大量色表资源，可供 Matplotlib、Gnuplot 或 VMD 使用。获取色表时只需提取其对应的 RGB 数值。若要将外部色表应用于 VMD，需导入 1024 个 RGB 值，或在需要时进行插值以补全颜色数据。

---

## 20. VMD Color Scale Bar 插件功能

Color Scale Bar 插件用于将 VMD 内部的颜色映射绘制为可视化的颜色条。通过 Extensions - Visualization - Color Scale Bar 菜单可调用此插件。插件脚本位于 VMD 目录下的 `plugins/noarch/tcl/colorscalebar1.4/colorscalebar.tcl`，允许用户读取 `colorinfo num` 和 `colorinfo max` 来建立颜色与数值的映射关系。

---

## 21. VMD Throb 颜色显示机制

Throb 颜色模式依据 wall clock time 使颜色产生闪烁效果。这种动态颜色变化可用于数据更新，实现实时绘图和视觉提醒。在任何时刻，Throb 闪烁所显示的颜色均保持一致，与空间位置无关。

---

## 22. VMD VolumeSlice 绘制方式

VolumeSlice 功能依据颜色数值进行切片绘制，生成的颜色图是观察体积数据的有效手段。该模式支持按 BGR 颜色顺序进行显示。在 VMD 中生成的颜色图可导出，建议使用 VESTA 或 Multiwfn 进行观察，以获得更佳的视觉效果。

---

## 23. VMD 动态显示的数据范围设置

在 Graphics - Representations 的 Graphical Representations 界面中切换至 Trajectory 标签页，可修改 Color Scale Data Range。修改数据范围等同于使用 `mol scaleminmax` 命令。此操作不会改变渐变色的定义，仅影响颜色在特定数值区间内的分布。

---

## 24. VMD 绘图对象的颜色索引使用

利用 graphics 的 draw 命令绘制用户自定义线条或圆柱体时，可指定颜色索引。颜色索引的有效范围通常在 33 到 1056 之间。在此范围内指定索引可应用自定义的渐变色定义。

---

## 25. VMD PaletteTool 插件功能

PaletteTool 插件位于 Extensions - Visualization - PaletteTool 菜单下，功能与 Color Scale Bar 类似，更为直观。该插件脚本位于 `plugins/noarch/tcl/palettetool1.0/palettetool.tcl`。PaletteTool 能够列出 VMD 当前使用的全部 RGB 颜色，并读取 `colorinfo num`。

---

## 26. VMD 背景颜色的修改限制

VMD 的背景颜色修改仅支持定义顶部和底部的颜色，系统自动生成中间的过渡渐变色。用户无法通过常规方式修改中间过渡区域的 RGB 值或改变生成过渡色的方式。涉及背景颜色修改的设置不包含对中间色的直接控制。

---

## 27. VMD 调色板颜色定义文件

VMD 的元素、类别及各种颜色的定义存储在安装目录的 `scripts/vmd/colordefs.dat` 文件中。修改资料件可以调整系统内置的调色板设置。`colorinfo colors` 命令所列出的颜色即源于该文件的定义。

---

## 28. VMD 渐变色方法与参数调整

通过 Color Controls 面板可调整渐变色的 Method、Offset 和 Midpoint 参数。在内部操作中，这等同于使用 `color scale <method|midpoint|min|max>` 命令。这些调整直接影响 VMD 应用渐变色色块的方式，是修改如 ESPiso.vmd 或 IRIfill.vmd 等脚本时的常见操作。

---

## 29. VMD ColorID 颜色模式的索引

当显示模式设置为 ColorID 时，Graphical Representations 面面中指定的索引（如 33）可能不会生效。在脚本中指定索引时，通常使用 32 才能有效应用颜色。如果未设置渐变色，ColorID 模式会回退到常规颜色应用。

---

## 30. VMD 脚本中的颜色索引范围

涉及颜色修改的 VMD 脚本通常会将 33 到 1056 范围内的颜色索引视为一组。这些索引与系统内置的颜色定义（如元素颜色）可同时使用。

---

## 31. 外部渲染器与 VMD 截图的差异

使用外部渲染器（如 POV-Ray、Tachyon）渲染 VMD 图像与直接使用 OpenGL 截图存在差异。不同渲染算法会导致图像显示上的偏差，这种偏差主要体现在光影效果而非数据梯度。Snapshot 截图效果与 OpenGL 视图完全一致，但外部渲染通常能提供更好的光感和质感。

---

## 32. VMD 外部渲染器的接口问题

VMD 1.9.3 版本与外部渲染器的接口存在已知问题，特别是使用 POV-Ray 或 Wavefront OBJ 格式时。渲染结果可能会丢失信息，导致等值面仅能显示为白色。官方邮件列表中有关于此问题的讨论记录。

---

## 33. VMD Tachyon 渲染器的优势

Tachyon 是 VMD 自带且推荐使用的外部渲染器。其渲染效果通常优于直接使用 Snapshot 截图。Tachyon 对渐变色的展示较为忠实于原始设定，且渲染质量较高。
