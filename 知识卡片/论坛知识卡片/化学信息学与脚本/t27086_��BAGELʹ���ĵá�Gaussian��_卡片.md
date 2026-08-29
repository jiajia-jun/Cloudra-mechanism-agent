---
key: t27086
title: ��BAGELʹ���ĵá�Gaussian��BAGEL������CASPT2�����Ż��Ľű�
url: http://bbs.keinsci.com/thread-27086-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2021
cards: 17
---

# ��BAGELʹ���ĵá�Gaussian��BAGEL������CASPT2�����Ż��Ľű� — 知识卡片

## 1. gau_bag.sh 脚本功能与适用性

gau_bag.sh 脚本旨在解决 Gaussian 与 BAGEL 结合使用时的输入规范化问题。该脚本能够适应不同阶导数的计算需求，避免用户针对不同目的编写不同代码。用户只需将脚本放置在固定目录下即可使用。

---

## 2. BAGEL 几何优化与原脚本的局限性

原始脚本仅适用于一阶导数的计算，无法应用于二阶导数（如频率计算）。在 GV 等软件中观看 CASPT2 水平的势能面扫描动画时，二阶导数信息是必不可少的。

---

## 3. BAGEL 计算输出文件的保存机制

BAGEL 的几何优化过程会将“前一步”和“当前步”的波函数文件全部保存。每一帧对应的计算文件都会被保留，例如生成为 step_xxxx.bag.archive 文件。

---

## 4. 原始脚本的参数传递机制

原始脚本每次调用都需要读取原子坐标、基组、活化空间和电子态等参数。这些信息会被转换到 gjf 文件中，或通过 external 接口传递给 BAGEL 使用。

---

## 5. Gaussian 输出文件与 BAGEL 波函数的交互

原始 Gaussian 输出文件中不包含梯度信息，且无法直接导出波函数用于后续计算。若要提取波函数，需要从 BAGEL 输出文件中获取，而原脚本将必要信息打印在 Gaussian 输出文件中，省去了用户在文件间手动转换的步骤。

---

## 6. 环丁二烯 CASPT2 几何优化流程示例

以环丁二烯为例，使用该脚本结合 BAGEL 进行 CASPT2 优化。该过程包括准备初始坐标文件、进行 RHF 计算、确定活化空间、生成 CASSCF 输入文件以及最终调用 Gaussian 进行优化。

---

## 7. BAGEL 初始 RHF 计算输入文件 (c4h4s.bag.json)

c4h4s.bag.json 文件定义了分子的初始几何结构、基组 (cc-pvdz) 和密度拟合基组 (cc-pvdz-jkfit)。文件包含 "hf"、"save_ref" 和 "print" 模块，用于执行 RHF 计算并保存波函数文件 (c4h4s.bag.archive) 和轨道文件 (c4h4s.bag.molden)。

---

## 8. 活化空间选择与轨道编号

使用 Multiwfn 查看 molden 文件，选取 4 个 $\pi$ 轨道和 4 个 $\pi^*$ 轨道作为活化空间。这些轨道在 BAGEL CASSCF 输入文件中的编号对应于 HOMO 和 LUMO 附近的轨道，类似于 Gaussian 中 guess(read,alter) 的功能。

---

## 9. BAGEL CASSCF 计算输入文件 (c4h4s+.bag.json)

c4h4s+.bag.json 文件通过 "load_ref" 读取上一步的波函数文件，并进行 CASSCF 计算。参数设置包括活化轨道数 `nact`: 4、非活化轨道数 `nclosed`: 12，以及具体的活化轨道编号 `active`: [13,14,15,20]。

---

## 10. Gaussian 接口 gjf 文件配置 (c4h4s.bag.gjf)

Gaussian 输入文件通过 external 关键字调用 gau_bag.sh 脚本，并传递核心参数：线程数 9、基组 cc-pvdz、密度拟合基组 cc-pvdz-jkfit、多重度 2、电荷 0、活化轨道数 4、闭壳层轨道数 12。优化路径中需包含 `nomicro` 和 `nosym` 关键字。

---

## 11. Gaussian 优化过程中的文件传递

Gaussian 运行时，BAGEL 计算产生的 archive 文件会被复制并重命名为 Gau-[PID].archive。每一步优化都会将上一步的 archive 作为当前步的参考文件，同时生成 ENERGY.out 和 FORCE_0.out 供 Gaussian 读取能量和梯度。

---

## 12. BAGEL 优化算法的局限性及解决方案

BAGEL 自带的优化算法在寻找过渡态或平衡位置时可能不稳定，甚至出现能量异常跳跃。解决方法是将优化步长半径固定为 0.1 Bohr，或者结合使用 Gaussian 的优化算法，利用其稳定性优势。

---

## 13. Gaussian external 接口脚本工作流程

Gaussian 将分子坐标、电荷、多重度等信息写入 Gau-[PID].EIn 文件。脚本读取该文件并调用 BAGEL 进行计算，计算得到的能量和梯度信息写入 Gau-[PID].EOu 文件。Gaussian 读取 EOu 文件后决定下一步的几何结构。

---

## 14. 脚本使用步骤：准备输入文件

需预先准备好包含 BAGEL CASSCF 单点计算任务的 .json 文件，并确保生成的 molden 和 archive 文件可用。使用 Multiwfn 检查轨道，若无问题则编写 .gjf 文件。

---

## 15. 脚本使用步骤：调用与配置

将 gau_bag.sh 放置在当前目录，并在脚本中填写用户信息及 CASSCF 活化空间信息。在 gjf 文件中通过 `external='bash gau_bagel.sh'` 调用脚本，并在 Gaussian 中提交任务。

---

## 16. BAGEL JSON 文件编写注意事项

BAGEL 输入文件格式对语法敏感，编写时需严格注意路径符号、引号和逗号的使用。这些细节错误会导致程序无法读取或运行失败。

---

## 17. 计算性能评估

该方法结合了 BAGEL 的高精度电子结构计算能力和 Gaussian 的高效几何优化算法。预计在不同计算节点上，此组合方案能提供比单独使用 BAGEL 更优的计算速度和稳定性。
