---
id: 143
title: 将Material Studio的xtd轨迹文件导出为xyz轨迹文件的方法
domain: 化学信息学与脚本
topic: MS_xtd轨迹转xyz格式Perl脚本
cards: 7
---

## 1. xtd文件轨迹信息存储位置
Material Studio (M$) 的 xtd 文件包含原子或粗粒化模拟中 bead 的轨迹信息，实际轨迹信息储存在同目录下同名的.trj 隐藏文件里（二进制文件）。
- 该格式为 MS 私有格式，需转换为通用格式才能在 VMD 等程序中进行分析。
- 一种转换方法是利用 MS 自带的 trj2ascii.exe 程序将.trj 文件内容转换为普通文本文件，再通过程序转为其它轨迹格式，但此步骤较为麻烦。

---

## 2. xtd转xyz的Perl脚本原理
另一种转换方法是利用 MS 内部支持的 Perl 脚本，循环读取每一帧每一个原子或 Bead，将其坐标属性按照 xyz 坐标格式写入外部文该资料件。
- 生成的 xyz 轨迹文件可被 VMD 等程序直接载入。

---

## 3. xtd2xyz全原子轨迹转换脚本使用方法
将脚本内容复制到后缀名为.pl 的文本文件中，在 MS 里将此.pl 文件加入项目，并将其移动到要转换的 xtd 文件所在目录。
- 需修改脚本中的 my $doc = $Documents{"./benzene.xtd"}; 为实际要转换的文件名。
- 保持脚该资料件窗口激活状态，选择 tools-scripting-debug（或按 F5、工具栏蓝色三角按钮）开始转换。
- 转换结束后在当前目录下输出 trj.txt 文件，将后缀改为.xyz 即可被 VMD 等程序读取。

---

## 4. 转换脚本运行模式与速度差异
debug 模式对于大体系、帧数较多的轨迹转换速度较慢，建议使用 tools-scripting-Run on server 模式运行以显著提高转换速度。
- 使用 Run on server 模式时，trj.txt 将生成到新目录，当前目录下的其它文件也会被强制复制一份过去。

---

## 5. 指定帧数范围输出的方法
脚本默认转换所有帧，若需转换指定帧数范围，需修改代码中的帧号变量。
- 将 my $framebegin=1; 和 my $frameend=10; 改为自定的起止帧号。
- 使用时需先将 my $frameend=10; 行前面的注释符号去掉。

---

## 6. 周期性体系轨迹转换注意事项
对于周期性体系，转换出的轨迹样式取决于 MS 中的显示设置。
- 如果在 display style-lattice 中在某个方向上多显示一个周期，转换出的轨迹在相应方向上也会多出一倍原子。
- Default、In-Cell、Original 等不同的显示模式下转换出的原子坐标也会相应有所不同。

---

## 7. 粗粒化轨迹转换脚本xtdbead2xyz
名为 xtdbead2xyz 的 Perl 脚本专门用于转换粗粒化模拟（如 Mesocite）中以 bead 描述粒子的 xtd 轨迹，不能转换全原子轨迹。
- 脚本代码中使用 $doc->DisplayRange->Beads 获取 bead 粒子。
- 输出格式使用 $Bead->Name 作为元素符号列，用法与全原子转换脚本相同。
