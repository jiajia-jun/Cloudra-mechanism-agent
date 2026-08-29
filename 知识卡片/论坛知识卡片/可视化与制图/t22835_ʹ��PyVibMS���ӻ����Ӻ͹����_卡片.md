---
key: t22835
title: ʹ��PyVibMS���ӻ����Ӻ͹����е���ģʽ
url: http://bbs.keinsci.com/thread-22835-1-1.html
domain: 可视化与制图
source: keinsci
year: 2021
cards: 22
---

# ʹ��PyVibMS���ӻ����Ӻ͹����е���ģʽ — 知识卡片

## 1. PyVibMS 简介

PyVibMS 是一款开源的 PyMOL 插件，用于在 PyMOL 中可视化分子和固体的振动模式。该插件支持跨平台使用，源代码托管于 GitHub。它旨在补充 PyMOL 在计算化学振动分析可视化方面的功能，特别是处理晶体和周期性体系。

---

## 2. PyVibMS 支持的计算软件

PyVibMS 支持 ORCA、xtb 和 Q-Chem 等计算化学软件输出的振动文件。通过特定转换工具，它也可以支持 Gaussian 和 VASP 的格式。对于 CRYSTAL 软件输出的振动文件，PyVibMS 也能进行可视化。

---

## 3. PyMOL 的版本选择

PyMOL 分为商业版和开源版。商业版需要许可证，部分高级渲染功能可能受限，而教育版证书仅适用于教学演示。为了获得完整功能并避免许可证麻烦，推荐在科研中使用开源版本的 PyMOL。PyVibMS 同时兼容商业版和开源版 PyMOL。

---

## 4. 商业版 PyMOL 的安装方法

商业版 PyMOL 的安装程序适用于 Windows 和 Mac 系统，Linux 系统通常需下载压缩包。在 Linux 终端中，进入解压后的 pymol 文件夹，执行 `chmod +x pymol` 赋予执行权限，然后运行 `./pymol` 即可启动。若已获取许可证文件，需将其放置在指定目录。

---

## 5. Windows 下安装开源版 PyMOL

在 Windows 下安装开源版 PyMOL 需先下载预编译的 whl 文件（如 `pymol-2.5.0a0-cp38-cp38-win_amd64.whl`）。需安装 64 位 Anaconda，并创建一个 Python 3.8 的环境。通过 `conda install` 安装必要的依赖库后，使用 `pip install` 命令安装下载的 whl 文件，最后输入 `pymol` 启动。

---

## 6. Linux 下安装开源版 PyMOL

在 Linux 系统下，可利用系统包管理器直接安装开源版 PyMOL。在 Ubuntu 系统中，使用命令 `sudo apt-get install pymol`。在 CentOS 系统中，使用命令 `sudo yum --enablerepo=epel install pymol` 即可完成安装。

---

## 7. Mac 下安装开源版 PyMOL

在 Mac 系统下安装开源版 PyMOL，需要先安装 MacPorts。安装 MacPorts 后，在终端执行命令 `sudo port install pymol` 即可完成安装过程。

---

## 8. PyVibMS 插件的安装

PyVibMS 插件的安装需在 PyMOL 软件安装之后进行。从 GitHub 下载 PyVibMS 的 Zip 压缩包并解压。打开 PyMOL，进入 Plugin -> Plugin Manager 菜单，选择 Install New Plugin 标签页，点击 Choose file 选中解压文件夹中的 `__init__.py` 文件，按提示确认即可完成安装。

---

## 9. 可视化 Gaussian 振动输出

在 PyVibMS 面板中选择 Input File，加载 Gaussian 的 log 文件，文件类型识别为 XYZ 或 Gaussian 09/16。勾选 Has Vib. Info 并点击 Load，PyMOL 将显示分子结构，插件界面列出振动模式编号、频率（cm⁻¹）和对称性。选中某模式后点击 Start Animation 可显示振动动画。

---

## 10. 振动位移矢量显示与调整

在显示分子振动动画时，勾选 Displacement Vectors 选项，PyMOL 会在原子上显示箭头表示振动矢量。可以通过滑块调整振动幅度。若需反转矢量方向，可取消并重新勾选 Displacement Vectors 选项，或者调整参数（如设为 50%）来实现反转。

---

## 11. PyMOL 高质量图片导出

在 PyMOL 中导出高质量渲染图时，可点击 File -> Export Image As -> PNG，在弹出的窗口菜单中选择 ray trace with transparent background。也可以在命令行输入 `ray` 命令进行渲染。注意，商业版 PyMOL 若无有效许可证，渲染出的图片可能会带有水印。

---

## 12. 商业版 PyMOL 导出振动动画 GIF

在商业版 PyMOL 中，选中某一振动模式后，点击 File -> Export Movie As -> MPEG。在弹出的窗口中，将 Rendering 选为 Ray(slow)，Encoder 选为 convert，格式路径选为 GIF，即可导出 GIF 动画。

---

## 13. 开源版 PyMOL 导出振动动画 GIF

开源版 PyMOL 不支持直接导出 GIF，需先导出 PNG 序列。点击 File -> Export Movie As -> PNG Images，Rendering 选为 Ray(slow)，选择一个空文件夹作为保存路径。生成一系列编号的 PNG 图片后，上传至 ezgif.com 等在线工具，调整播放速度或延迟后生成并下载 GIF。

---

## 14. VASP 振动文件数据准备

可视化 VASP 的振动输出需要 OUTCAR 和 CONTCAR 文件。需将 CONTCAR 的内容（晶胞信息）复制并粘贴到 OUTCAR 文件的第一行，生成一个新的 `.out` 后缀文件（如 `Si_OUTCAR.out`）。该文件包含了原子坐标、模式矢量、周期性边界条件（PBC）及元素组成信息。

---

## 15. VASP 振动模式可视化步骤

在 PyVibMS 中加载处理后的 VASP 输出文件，文件类型识别为 VASP 5.x。勾选 Has PBC 和 Has Vib. Info 并点击 Load。PyMOL 将显示晶胞结构，插件界面列出振动模式，前三个频率为 0 的模式对应平动。可以使用 Unit/Primitive Cell 按钮切换原胞或超胞显示。

---

## 16. VIBC 晶体超胞构建与振动显示

为了更直观地观察晶体振动，可以使用 Make Supercell 按钮将结构扩展为超胞。构建超胞后，晶胞中的重复单元将同时显示，通过动画可以观察到原子在长程结构下的同步振动情况。

---

## 17. CRYSTAL 二维水结构振动可视化

加载 CRYSTAL17 的输出文件（如 `crystal_2d-water_translate.out`），识别为 CRYSTAL17 格式。勾选 Has PBC 和 Has Vib. Info 并点击 Load。PyMOL 将显示二维水分子层结构，插件界面会列出 9 个振动模式，其中前 3 个频率为 0 的模式对应平动。

---

## 18. 通用 XYZ 文件振动可视化准备

对于 PyVibMS 原生不支持的软件输出，可使用通用格式进行可视化。需准备一个标准的 XYZ 坐标文件和自定义的 mode 文资料件。XYZ 文件描述原子结构，mode 文件包含原子数、模式数、频率、对称性及各原子的位移矢量数据。

---

## 19. 通用 mode 文件格式规范

通用 mode 文件的首行格式为 `原子数 模式数`，随后的数据块以 `N 频率 对称性 模式序号` 开头。接下来按原子顺序列出 X、Y、Z 三个方向的位移分量。每个模式的数据块结束后，开始下一个模式的数据，文件以 `END` 结尾。`#` 符号后的内容为注释。

---

## 20. 利用 PyVibMS 显示周期性结构

除了显示振动模式，PyVibMS 还可以利用 PyMOL 的可视化功能显示分子和晶体结构。对于分子，直接加载 XYZ 文件即可。对于晶体或周期性结构，需在 Dimensions 菜单设置维度，并输入 a1-a3 晶格矢量信息，以正确显示周期性结构。

---

## 21. 一维聚乙炔结构显示示例

加载一维聚乙炔的原子坐标文件（如 `cell-content.xyz`）后，PyMOL 显示单胞原子。在 Dimensions 菜单将维度设为 1。读取包含晶格矢量数据的文资料件，将数据复制到 a1 输入框中（需去除逗号），点击对应按钮即可显示沿一维方向延伸的聚乙炔链结构。

---

## 22. PyVibMS 相关文献

PyVibMS 的相关方法和应用发表在 *Journal of Molecular Modeling* 上。引用文献为：Tao, Y., Zou, W., Nanayakkara, S. et al. PyVibMS: a PyMOL plugin for visualizing vibrations in molecules and solids. J Mol Model 26, 290 (2020).
