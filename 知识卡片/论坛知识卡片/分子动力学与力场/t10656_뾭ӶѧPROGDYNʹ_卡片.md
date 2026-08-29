---
key: t10656
title: �뾭����Ӷ���ѧ����PROGDYNʹ�ý̳�
url: http://bbs.keinsci.com/thread-10656-1-1.html
domain: 分子动力学与力场
source: keinsci
year: 2018
cards: 14
---

# �뾭����Ӷ���ѧ����PROGDYNʹ�ý̳� — 知识卡片

## 1. PROGDYN 程序简介与功能

PROGDYN 是基于 bash 和 awk 脚本的程序，用于执行直接分子动力学模拟，特别适用于研究分叉点以及隐式势能面下的反应速率常数。该程序主要用于无法通过过渡态理论(TST)预测反应路径的情况，只能进行分叉的动力学模拟。PROGDYN 的源代码修改十分方便，适合模拟不同体系。

---

## 2. PROGDYN 运行前的文件准备

使用 PROGDYN 之前需要准备两个主要文件：freqinHP 和 progdyn.conf。freqinHP 由 Gaussian 频率计算生成，需在计算时加上 freq=hpmode 关键字以输出所需的有效数字。progdyn.conf 是配置文件，用于定义计算方法、电荷、多重度、内存和处理器数等参数。

---

## 3. 动力学轨迹的初始化流程

PROGDYN 从 freqinHP 中读取初始结构，并通过不同的方式进行初始化。每一轨迹的起始结构均从 freqinHP 中选取，随后运行分叉的动力学模拟。每一个量子力学(QM)计算步骤对应时间轴上的一个点，直至轨迹达到终止条件。

---

## 4. PROGDYN 程序目录结构说明

PROGDYN 的主程序文件位于 binall400 目录下，只需调用其中的 randgen 即可运行。n400 目录下通常只需存放一个文件 progdyn.conf。binall400 目录内包含一系列文件，其中 freqinHP 存放频率数据，progdynstarterHP 是启动脚本，progdyn.conf 是基于模板的配置文件。

---

## 5. 环境变量配置依赖

在使用 PROGDYN 之前，必须确保系统已正确安装 openbabel。如果是在集群上运行，通常需要取消注释并设置关于 babel 的库目录和数据目录环境变量（如 BABEL_LIBDIR 和 BABEL_DATADIR）。同时需要正确设置 LD_LIBRARY_PATH 以包含必要的库文件路径。

---

## 6. 启动脚本 progdynstarterHP 参数设置

在 progdynstarterHP 脚本中，需要设置多个路径变量：randdir 指向 randgen 所在位置，proggramdir 指向 binall400 文件夹所在位置，freqfile 指向 freqinHP 文件。此外，还需设置 g09root 指向 Gaussian 安装目录，并加载 g09.profile。脚本会清理旧的状态文件（如 nogo, diagnostics, goingwell, tempdone），并检查输入文件 g09.com 是否存在，若存在则删除其中的 guess=tcheck 行以避免使用 checkpoint 文件。

---

## 7. progdyn.conf 核心计算参数配置

progdyn.conf 文件定义了轨迹计算的参数，包括方法（如 MP2/cc-pvdz）、非标准计算开关（nonstandard）、电荷（charge）、多重度（multiplicity）、处理器数（processors）和内存（memory）。method 项会被直接复制到 Gaussian 输入文件中。若使用非标准 route，需将 nonstandard 设为 1 并创建一个名为 "nonstandard" 的文件包含路由行。

---

## 8. 自定义轨迹分析文件 proganal

proganal 文件用于实时监控轨迹，包含定义几何参数（如键长距离）和判断逻辑的代码。例如，可以定义 C2C6=Distance(2,6) 等变量，并使用 printf 输出当前值。通过 if 语句判断特定条件（如键长小于阈值）来打印产物信息（如 "Vinylfuran is dienophile XXXX"）或终止条件（如 "Too many points"）。

---

## 9. 轨迹终止条件的设置

修改 proganal 文件是实现自定义轨迹终止步骤的关键，其中的逻辑必须与 freqinHP 中的定义一致。通常通过判断特定键长是否小于临界值来判定反应是否发生并形成产物阶段，从而终止该轨迹。

---

## 10. 运行命令与输出文件

运行 PROGDYN 时需在 n400 目录下创建 tmp 目录存放临时文件，执行命令为 `/binall400/progdynstarterHP tmp`。运行完成后，n400 目录下会生成多个文件，包括 g09.com、geoPlusVel、geoRecord、Echeck、dynfollowfile、runpointnumber 和 isomernumber。

---

## 11. 输出文件含义说明

isomernumber 指示当前是第几条轨迹，一条轨迹完成后程序会继续从初始结构开始生成新的轨迹。geoPlusVel 记录当前的结构和所有原子的速度，geoRecord 记录从初始结构到当前的结构和速度，dynfollowfile 记录 proganal 指定的监控轨迹信息。

---

## 12. 轨迹初始分布模式与错误处理

如果轨迹的第二个点出现 "bad total energy" 错误，意味着从初始点出发的步长太大，被判断为发生了大变化，程序将重置并开始一条新轨迹。在 progdyn.conf 中有一个 initialdist 选项，用于指定轨迹的初始化分布方式。除了基于反应势能面的频率模式外，还有其他模式可用于初始位置选择，选项 4 被推荐用于避免 "bad total energy" 错误。initialdist 默认值通常为 4，但用户可根据实际情况调整。

---

## 13. 计算资源与效率建议

Gaussian 的计算效率对整体速度影响较大，建议一个 PROGDYN 任务只使用一个节点。配置示例中建议将 CPU 和内存设置得较小（如 3 个处理器，7GB 内存）。根据 Singleton 的习惯，可以在一个 20 核的节点上同时运行 6 个任务以利用资源。

---

## 14. 模拟结果分析与应用

通过 PROGDYN 得到的轨迹可用于分析产物分布信息，如可能得到的两种产物（Vinylfuran 和 Cyclopentadienone，即双环戊二烯）。通过统计大量轨迹的产物比例，可以推断反应的选择性。文中的模拟结果显示比例为 1.47，与实验值 1.6 以上较为接近。
