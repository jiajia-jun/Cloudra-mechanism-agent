---
key: t58337
title: ����һ����VS Code�п��ӻ���༭ԭ�ӵĲ��ACoord
url: http://bbs.keinsci.com/thread-58337-1-1.html
domain: 可视化与制图
source: keinsci
year: 2026
cards: 20
---

# ����һ����VS Code�п��ӻ���༭ԭ�ӵĲ��ACoord — 知识卡片

## 1. ACoord 工具简介

ACoord (Atomic Coordinate Toolkit) 是一款 Visual Studio Code 扩展，支持直接查看、编辑和导出分子/晶体坐标。

---

## 2. 远程查看与修改结构

该扩展配合 VS Code 的 Remote (SSH) 功能，可实现在远程服务器上直接查看和修改结构。

---

## 3. 3D 查看与编辑功能

3D 查看器基于 Three.js 开发，支持选中、平移、旋转等编辑操作，以及轨迹播放、帧数和播放速度控制。

---

## 4. 轨迹文件格式支持

轨迹播放功能支持 XYZ、QE 输出日志、XDATCAR 和 OUTCAR 文件。

---

## 5. 视图与显示模式

该工具支持投影模式切换（透视/正交）、坐标轴显示、氢键显示，以及原子标签的颜色、边框和实心/空心样式调整。

---

## 6. 原子可视化调整

支持从原子中心或仅原子位置进行观察，并可调整原子大小与场强度。

---

## 7. 文件导出功能

通过“Save As”功能可实现格式转换，并支持从当前 3D 视图导出为 PNG 图片。

---

## 8. 支持的输入输出格式

ACoord 支持的文件格式包括 XYZ、CIF、POSCAR/XDATCAR/OUTCAR、PDB (支持周期性)、Gaussian input (.gjf)、ORCA input (.inp)、ABACUS STRU (.stru)、Quantum ESPRESSO input (.in / .pwi) 以及 Quantum ESPRESSO output log (.out / .pwo / .log)。

---

## 9. 安装方式：VS Code 商店

可在 VS Code 内置的扩展商店中搜索 ACoord 并进行安装。

---

## 10. 安装方式：源码安装

支持通过 GitHub 仓库 (https://github.com/wxia529/acoord) 构建源码进行安装。

---

## 11. 基本使用步骤

在 VS Code 中打开支持的结构文件，点击编辑器上方的预览图标进入 3D 视图，即可在 3D 视图中进行查看和修改原子坐标，操作完成后使用 Save 或 Save As 保存。

---

## 12. 原子选择操作

在画布中点击原子可选中，按住 Ctrl (Windows/Linux) 或 Cmd (macOS) 可进行多选或取消选择，按住 Shift 并拖拽可保持当前选择范围。

---

## 13. 原子移动操作

在画布中按住 Shift 并拖拽选中的原子即可移动其位置。

---

## 14. 旋转选中项操作

选择旋转轴（X/Y/Z），然后拖动角度滑块（0~360度）即可对选中内容进行旋转。

---

## 15. 修改元素类型

在“Change Element”菜单中选择目标元素，点击“Apply”按钮可修改选中原子的元素种类。

---

## 16. 添加或删除原子

使用“Quick Add”按钮可添加原子，使用“Delete”按钮可移除选中的原子。

---

## 17. 几何测量功能

选中 2 个原子可测量键长，选中 3 个原子可测量键角。

---

## 18. 对齐镜像功能

选中镜像原子，将选中的原子作为参考点，其他原子将基于“参考原子-镜像原子”的矢量方向移动直至对齐。

---

## 19. 调整显示参数

可通过“自动缩放”或“手动缩放”调整显示效果，在“设置脚本”中输入“原子尺寸”可优化图形显示。

---

## 20. 支持与反馈

欢迎提交 Issue 或提出新功能建议，联系方式为 GitHub: https://github.com/wxia529/acoord。
