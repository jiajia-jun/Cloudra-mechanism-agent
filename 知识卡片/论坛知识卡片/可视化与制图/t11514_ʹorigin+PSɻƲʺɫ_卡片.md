---
key: t11514
title: ʹ��origin+PS���ɻ��Ʋʺ�ɫ����������ͼ
url: http://bbs.keinsci.com/thread-11514-1-1.html
domain: 可视化与制图
source: keinsci
year: 2018
cards: 6
---

# ʹ��origin+PS���ɻ��Ʋʺ�ɫ����������ͼ — 知识卡片

## 1. Origin 与 Photoshop 结合生成光谱色图

使用 Origin 绘制数据图表并导入 Photoshop，通过特定渐变工具可将图表转化为带有光谱背景颜色的效果，适用于光谱数据的可视化展示。
- 操作流程为先在 Origin 中绘图并复制图片至 Photoshop，随后进行渐变映射。

---

## 2. Photoshop 光谱渐变工具文件加载

在 Photoshop 中选择渐变工具并载入名为 `spectrum.grd` 的渐变文件，可加载预设的光谱渐变配置。
- 该文件名为 `spectrum.grd`，载入后 Photoshop 的渐变编辑器中将出现名为 `spectrum` 的渐变选项。

---

## 3. Photoshop 魔棒工具选择与渐变映射

在 Photoshop 中使用魔棒工具点击选择图表中的曲线区域，确定保留选区后对 `spectrum` 渐变执行渐变映射操作。
- 操作时需注意保持选区为曲线区域，以确保颜色仅映射至图表曲线部分。

---

## 4. 渐变映射的色彩范围限定与拖拽技巧

对曲线区域进行颜色拖拽时，按住 Shift 键并将起始点和结束点分别限定在 380nm 和 780nm 处，可使颜色映射范围准确对应可见光区域（380-780nm）。
- 拖拽过程中必须保持 Shift 键按下，以确保生成的渐变是水平的，从而保证图表颜色的准确性。

---

## 5. Python 脚本绘制光谱色图的环境依赖

使用名为 `Rainbow_spectrum.py` 的 Python 脚本可替代 Photoshop 流程绘制光谱色图，运行前需安装 Python 环境以及 `scipy`、`numpy`、`matplotlib` 依赖库。
- 该脚本代码资源托管于 GitHub 地址 `https://github.com/lizhiq16/py_color_draw/tree/main/`。

---

## 6. Python 脚本绘制光谱色图的操作方法

将脚本 `Rainbow_spectrum.py` 与数据文件放置于同一目录，数据文件第一列为波长、第二列为强度（空格分隔），在当前目录执行命令 `python Rainbow_spectrum.py` 即可生成图片。
- 运行脚本后会提示输入数据文件名（如 `spectrum.txt`），回车后在当前目录生成结果文件 `Rainbow_spectrum.png`。
