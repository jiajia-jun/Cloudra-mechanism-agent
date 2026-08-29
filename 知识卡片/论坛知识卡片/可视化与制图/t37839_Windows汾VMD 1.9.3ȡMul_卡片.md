---
key: t37839
title: Windows�汾VMD 1.9.3��ȡMultiwfn chg�ļ��Ĳ����
url: http://bbs.keinsci.com/thread-37839-1-1.html
domain: 可视化与制图
source: keinsci
year: 2023
cards: 9
---

# Windows�汾VMD 1.9.3��ȡMultiwfn chg�ļ��Ĳ���� — 知识卡片

## 1. .chg 文件格式

.chg 文件由 Multiwfn 生成，其格式包含5列数据。第1列为原子序数，第2-4列分别为XYZ坐标（埃单位），第5列为原子电荷，数据列之间以空格分隔。

---

## 2. VMD 读取 .chg 文件的兼容性

VMD 官方目前尚未稳定支持直接读取 .chg 文件。在 Windows 系统下使用 VMD 1.9.3 版本，可以直接加载并显示 .chg 文件中的原子坐标和电荷信息。

---

## 3. Windows 系统下的 VMD 版本选择

Windows 系统下提供的 VMD 1.9.3 分为 32 位和 64 位版本。下载时需注意区分位数，论坛提供的压缩包中包含了适用于 Windows 系统的 VMD 1.9.3 32 位和 64 位版本。

---

## 4. 插件功能更新 (2024.06.10)

更新后的插件增加了广泛支持某些 tpr 文件读取的功能。插件支持写入 xtc 轨迹格式，可替换 VMD 原生的 trr 格式以减小体积。插件支持从 Gaussian gjf 文件中读取结构，并支持 SDF 分子格式的结构可视化。

---

## 5. 插件安装步骤

解压插件压缩包后，根据本地安装的 VMD 位数选择对应的文件夹。找到 VMD 安装路径下的 molfile 文件夹，如 `D:\VMD\plugins\WIN32\molfile` 或 `D:\VMD\plugins\WIN64\molfile`，将相应的 .so 文件移动复制到该 molfile 文件夹中。

---

## 6. VMD 加载与显示电荷

启动 VMD 终端并确保插件已安装后，可直接读取 .chg 文件。文件会自动加载原子坐标及对应电荷，通过 Graphics -> Representations 窗口中的 Coloring Method -> Charge 选项可按电荷着色。

---

## 7. .chg 文件的数据精度要求

为与 VMD 内部匹配，导出的 .chg 文件中电荷数据仅建议保留6位小数。VMD 内部只读取 float 类型，保留过多小数位无效。

---

## 8. tpr 插件说明与 GROMACS 版本兼容性

tprpluginX.so 是专门为读取 GROMACS 的 tpr 文件编写的插件，VMD 1.9.4 可能内置了类似功能。只要 GROMACS 版本不大于 4（且年份在 2023 年前），通常可自动读取，无需该插件。

---

## 9. 旧版插件对新版 GROMACS 的局限性

对于新版 GROMACS 生成的体系，如果 VMD 或该插件无法直接读取 tpr 文件，可以通过 xtc 轨迹文件进行可视化。在轨迹模式下添加右键菜单功能可以显示原子序数，但利用轨迹中的原子生成骨架等处理可能不准确。
