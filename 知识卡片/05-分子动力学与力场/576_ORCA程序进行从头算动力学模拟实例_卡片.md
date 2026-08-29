---
id: 576
title: 使用ORCA做从头算动力学(AIMD)的简单例子
url: http://sobereva.com/576
domain: 分子动力学与力场
topic: ORCA程序进行从头算动力学模拟实例
cards: 12
---
## 1. ORCA做AIMD的优势与适用范围

ORCA量子化学程序拥有BOMD形式的从头算动力学功能，因其DFT计算效率高、使用方便，是做孤立体系AIMD的首选程序之一。相比于Gaussian的ADMP或BOMD，ORCA的输入文件更直观、速度更快且具备像样的热浴。ORCA只适合跑孤立体系的从头算动力学，若要做周期性体系的从头算动力学，CP2K是最佳选择。
- 相关研究案例可见：Chem. Asian J., 16, 56 (2021); Carbon, 171, 514 (2021); Inorg. Chem., 62, 19986 (2023); ChemPhysChem, 25, e202400377 (2024)

---

## 2. Multiwfn生成ORCA的AIMD输入文件

使用Multiwfn程序可以方便地生成ORCA AIMD任务的标准输入文件，支持载入gjf等多种含结构信息的文件。操作步骤为：启动Multiwfn -> 载入结构文件（如complex.gjf） -> 输入`oi` -> 选择任务类型`0` -> 选择分子动力学`6` -> 选择计算级别（如`1`对应B97-3c）。
- 生成后需根据实际情况修改输入文件中的特定参数。

---

## 3. ORCA输入文件关键参数设置

在生成的ORCA AIMD输入文件（如complex.inp）中，需根据计算资源调整并行和内存设置：`%maxcore 10000`设定每个进程最大内存为10000MB；`%pal nprocs 10 end`设定使用10个核心。由于ORCA做DFT的AIMD并行效率不理想，小体系使用过多核心可能导致速度变慢，一般设为10核即可，多核机器建议通过绑定CPU内核同时跑多个任务。
- 相关技巧见：《通过设置CPU内核绑定降低ORCA同时多做任务的耗时》

---

## 4. AIMD模拟的步长与温度初始化

ORCA AIMD输入文件中，`timestep 1.0_fs`设置动力学步长为1飞秒，这对常温模拟是安全的，更高温度或追求绝对稳妥时可设为0.5 fs。`initvel 298.15_K no_overwrite`设置根据298.15 K温度通过Maxwell分布随机初始化原子速度，且若已有速度信息则不覆盖。
- 步长过大可能导致动力学不稳定。

---

## 5. AIMD模拟的热浴与轨迹输出设置

`thermostat berendsen 298.15_K timecon 30.0_fs`设置使用Berendsen热浴将温度控制在298.15 K，耦合时间常数为30 fs。`dump position stride 1 format xyz filename "pos.xyz"`设置每一步将当前坐标写入当前目录的pos.xyz文件，生成多帧xyz格式的轨迹文件。
- ORCA 5.0及以后版本支持更好的velocity rescale (CSVR) 热浴。

---

## 6. 质心约束与模拟步数限制

`constraint add center 0..22`将整个体系（0到22号原子）的质心约束在初始位置，以防止模拟过程中因数值问题导致整体漂移。`run 2000`设置总共运行2000步（此处为2 ps），建议每次运行步数不超过3000步，因为超过2000步后单步耗时可能逐渐上升；若需更长时间，应分段运行。
- 对于ORCA 5.0及以后版本，应去掉constraint行并将run行改为`run 2000 CenterCOM`。

---

## 7. ORCA AIMD的续跑功能

在ORCA AIMD输入文件的`%md`块中，`restart ifexists`选项被默认注释掉。若需要续跑且当前目录下存在之前运行产生的.mdrestart文件，取消该行的注释即可让任务延续之前AIMD的最后状态续跑，新轨迹会续写在原有轨迹文件后面。此时`initvel`应被注释，以避免重新生成初速度。
- 续跑文件由complex.mdrestart提供，包含每一步的时间、坐标、速度和受力信息。

---

## 8. ORCA AIMD的中间文件与分析

ORCA在AIMD模拟过程中会产生complex.md.log（MD模块输出信息）、complex.mdrestart（用于续跑的文件）、complex-md-ener.csv（包含每步时间、耗时、温度、能量等信息的CSV文件）。`dump gbw`相关的行被注释掉，若取消注释可每隔指定步数保存gbw波函数文件，利用Multiwfn批量分析可考察动力学过程中的电子结构变化。
- 详细分析方法见：《详谈Multiwfn的命令行方式运行和批量运行的方法》第4节

---

## 9. 使用VMD观看与调整AIMD轨迹

使用VMD程序观看ORCA输出的pos.xyz轨迹文件，建议修改VMD初始化文件添加自定义命令bt，以便播放轨迹时每帧自动更新连接关系。在VMD文本窗口输入bt更新成键，输入bw将背景设为白色，在Graphics - Representation中将Drawing Method改为CPK即可观看动画。
- 若要同步显示帧号，见《使VMD播放轨迹时同步显示帧号》

---

## 10. VMD测量距离随时间的变化

在VMD中按键盘2键后点击两个原子中心可添加Bond label显示距离，在Graphics - Labels的Bonds选项卡中点击Graph和Show preview可预览距离随时间的变化曲线。点击Graph按钮可在大窗口查看曲线，Labels窗口中的save按钮可将距离数据保存为文该资料件用于Origin绘图。
- 示例显示N-H键在约60 fs基本形成。

---

## 11. ORCA做AIMD的计算级别推荐

ORCA做AIMD时，B97-3c是一个廉价且不错的计算级别，ORCA会自动启用RIJ加速，适合描述大多数体系。但对于特定体系如18碳环，纯泛函描述会失败，此时应使用ωB97X-D3等方法。
- B97-3c不适合所有情况，具体讨论见Carbon, 165, 468 (2020)。

---

## 12. AIMD模拟的时间尺度与策略建议

以几十核服务器的能力，使用ORCA的B97-3c跑几十原子有机体系几十皮秒的动力学是可行的。为了节省昂贵的DFT计算资源，建议先用xtb基于GFN-xTB方法跑半经验动力学，以摸索温度、初始结构等条件，确认期望现象能出现后再用DFT跑。
- xtb动力学粗浅介绍见：《使用Molclus结合xtb做的动力学模拟对瑞德西韦(Remdesivir)做构象搜索》
