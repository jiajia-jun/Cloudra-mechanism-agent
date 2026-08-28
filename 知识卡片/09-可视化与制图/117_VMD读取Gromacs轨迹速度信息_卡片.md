---
id: 117
title: 使VMD读入Gromacs产生的trr轨迹中速度信息的方法
url: http://sobereva.com/117
domain: 可视化与制图
topic: VMD读取Gromacs轨迹速度信息
cards: 8
---

# VMD读取Gromacs轨迹速度信息 — 知识卡片

## 1. VMD读取Gromacs trr轨迹速度信息的现状

VMD的每帧数据结构包含vx, vy, vz三个速度字段，但直到1.9.1 beta版本，VMD在读取Gromacs产生的trr或gro文件时默认只读取坐标而不读取速度，导致速度字段为空白；相比之下，VMD读取LAMMPS轨迹时能够正常读取速度和受力信息。
- Gromacs的trr文件和gro文件均包含速度信息（gro文件中速度位于第45列之后）
- VMD目前无法直接读取这些文件中的速度信息

---

## 2. Gromacs轨迹输出速度信息的设置要求

若要让Gromacs输出的trr轨迹文件中每一帧结构信息都伴随对应的速度信息，必须在生成该trr文件所用的mdp文件中设置nstvout等于nstxout。
- nstvout和nstxout分别代表速度和坐标的输出频率

---

## 3. trr轨迹转换为单帧gro文件的操作步骤

假设要处理MIO.trr轨迹，首先建立一个文件夹（如vel），然后执行`trjconv -f MIO.trr -s MIO.tpr -o miku/t.gro -sep`并在提示时选择system；如果轨迹有101帧，将在miku目录下生成t0.gro到t100.gro的文件。
- -sep参数表示将轨迹的每一帧拆分成单独的文件
- 输出文件名中的数字与VMD中的帧编号相对应

---

## 4. VMD中加载轨迹与脚本的初始配置

在VMD中载入与MIO.trr对应的gro文件，删除初始帧后再载入MIO.trr；确保VMD中帧编号从0开始与.gro文件名对应；在TkConsole中执行TCL脚本前，需根据实际情况设置脚本的前四行变量：`set rootname /sob/water/miku/t`设定文件路径前缀，`set fpsinit 0`和`set fpsend 100`设定帧号范围，`set sel [atomselect top all]`设定读取所有原子的速度。
- 若只读取水的速度，需在trjconv时选择Water或SOL组，并将脚本中的all替换为waters

---

## 5. 使用TCL脚本从gro文件读取速度的代码逻辑

脚本通过循环帧号打开对应的.gro文件，跳过前两行注释和原子数行，逐行读取原子数据；使用`scan [string range $line 45 69] "%f %f %f" grovx grovy grovz`解析每行第45至69列的速度值，将其分别存入临时列表tmpvx, tmpvy, tmpvz；循环结束后使用`$sel set vx $tmpvx`等命令将速度写入VMD对应帧的vx, vy, vz字段。
- 该方法不依赖修改VMD或Gromacs源码，但读取速度比内部插件慢

---

## 6. 计算速度大小并载入VMD的脚本修改方法

如果感兴趣的是速度的大小而非有方向的速度矢量，可以在脚本读取速度时进行取绝对值运算，将`lappend tmpvx $grovx`修改为`lappend tmpvx [expr abs($grovx)]`，y和z方向同理。
- 此修改适用于仅关注速率数值的场景

---

## 7. 利用VMD User字段存储速度分量以实现分量着色

VMD的Trajectory-Velocity着色方式仅支持基于速度总大小着色，为了根据速度分量着色，可将速度分量分别载入User字段：修改脚本中的赋值部分为`$sel set user $tmpvx`、`$sel set user2 $tmpvy`、`$sel set user3 $tmpvz`，之后在Coloring method中选择Trajectory-User下的对应字段。
- VMD提供User, User2, User3, User4四个字段供用户自定义数据

---

## 8. 真空纳米水球电场模拟的可视化设置案例

在模拟11417个水分子构成的纳米水球在2V/nm电场下的运动时，将x, y, z方向速度载入User, User2, User3字段；在Graphics-Color...设置Method为BGR，建立显示方式：选择name OW，Drawing Method为Points，Size为3，Material为Transparent，Coloring method设为Trajectory-User-User，Color Scale Data Range设为-0.3到0.3，输入`pbc box -on`显示盒子。
- 蓝点和红点分别代表x负方向和正方向有较大速度的氧原子，绿点代表x方向速度接近0的氧原子
