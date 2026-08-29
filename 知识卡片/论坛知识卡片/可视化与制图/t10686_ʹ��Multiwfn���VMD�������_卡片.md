---
key: t10686
title: ʹ��Multiwfn���VMD�������ƹ��
url: http://bbs.keinsci.com/thread-10686-1-1.html
domain: 可视化与制图
source: keinsci
year: 2018
cards: 12
---

# ʹ��Multiwfn���VMD�������ƹ�� — 知识卡片

## 1. 轨道可视化准备工具与文件

轨道可视化需要准备 Gaussian 输出的 fchk 文件、Linux 版 VMD 1.9.3 (no cuda 版本) 以及 Multiwfn 3.5 版本。Multiwfn 用于处理 fchk 文件并生成轨道数据，VMD 用于轨道的渲染与绘图。

---

## 2. 使用 Multiwfn 生成轨道 Cube 文件

在 Multiwfn 中载入 fchk 文件后，依次选择功能编号 200（生成多个轨道波函数的 cube 文件）和 3（高质量网格，覆盖全体系，约 1728000 个点）。选择功能 1 将这些轨道的网格数据输出为独立的 cube 文件，以供 VMD 调用。

---

## 3. 指定轨道编号与 Cube 文件命名

在 Multiwfn 生成过程中，输入目标轨道对应的编号（如 5,6 分别对应 HOMO, LUMO）。输出的文件名将默认为 orb000005.cub 和 orb000006.cub，建议将其重命名为 orb-5.cub 和 orb-6.cub 以便于后续脚本处理。

---

## 4. VMD 图形界面可视化设置

在 VMD 中载入 orb-5.cub 文件，Graphics Representations 窗口中选择 Drawing method 为 CPK 以显示原子。对于新创建的图形表示，分别设置 Isosurface 的 isovalue 为 0.02 和 -0.02，并将 Draw Style 设为 Solid Surface。

---

## 5. 保存 VMD 可视化状态

完成图形设置后，在 VMD 主窗口选择 File -> Save visualization State，保存文件名为 orb-5（无需添加后缀）。保存此状态文件是为了后续利用批处理脚本生成高质量图片，且文件应与 cub 文件位于同一目录。

---

## 6. 可视化状态文件的脚本修改

可视化状态文件需要修改以去除坐标轴显示并调整文件路径。在文件中添加 `axes location off`，并使用文本编辑器将 cube 文件的绝对路径修改为相对路径（仅保留文件名），确保末尾包含 Tachyon 渲染命令。

---

## 7. Tachyon 渲染命令配置

VMD 状态文件末尾需添加 Tachyon 渲染命令以生成图片。命令格式为 `render Tachyon orb-5.dat "tachyon -aasamples 12 orb-5.dat -res 1200 900 -format BMP -o orb-5.bmp"`，使用此命令需要确认 VMD 已正确安装 Tachyon 模块。

---

## 8. 批量生成可视化状态文件

为了批量处理多个轨道文件，可复制并修改已生成的可视化状态文件。使用命令 `cp orb-5 orb-6` 创建副本，再利用 vi 编辑器的替换命令 `:1,$s/orb-5/orb-6/g` 将文件内所有的 orb-5 替换为 orb-6，即可生成对应 orb-6 的状态文件。

---

## 9. VMD 命令行渲染图片

通过 VMD 的命令行模式调用已修改好的可视化状态文件可以生成对应的 bmp 图片文件。执行命令格式为 `vmd < orb-5`，VMD 将在后台读取状态文件并执行渲染操作，无需打开图形界面。

---

## 10. Shell 脚本批量渲染

编写 Shell 脚本可实现当前目录下所有 cub 文件的自动批量渲染。脚本内容为遍历所有 `.cub` 文件，对每个文件执行 `vmd < ${inf%.cub}` 命令，从而自动生成每个轨道对应的可视化图片。

---

## 11. NTO 轨道可视化方法

自然跃迁轨道（NTO）的可视化方法与普通轨道相同，同样需要使用 Gaussian 生成的 fchk 文件。后续使用 Multiwfn 和 VMD 的处理步骤与普通轨道可视化的流程完全一致。

---

## 12. 可视化方法优势

使用该方法进行轨道可视化的优势在于能够保证所有轨道的视角、大小和显示风格完全一致。相比于使用 GaussView，该方法避免了手动调整导致的视角差异，且渲染参数可由用户根据喜好自定义配置。
