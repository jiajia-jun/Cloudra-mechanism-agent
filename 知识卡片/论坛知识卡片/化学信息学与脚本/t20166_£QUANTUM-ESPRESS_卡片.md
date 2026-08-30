---
key: t20166
title: �����£���QUANTUM-ESPRESSO-PWscf���ӻ����������pwin2gjf��pwout2gjf��gjf2pwin...
url: http://bbs.keinsci.com/thread-20166-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2020
cards: 23
---

# �����£���QUANTUM-ESPRESSO-PWscf���ӻ����������pwin2gjf��pwout2gjf��gjf2pwin... — 知识卡片

## 1. pwout2gauout.sh 脚本功能

pwout2gauout.sh 脚本能够将 PWscf 优化输出的输出文件转换为 Gaussian 输出文件。转换后的文件支持在 GaussView 中打开，方便查看每一帧的结构变化。

---

## 2. gjf2pwin.sh 脚本功能

gjf2pwin.sh 脚本用于将 gjf 文件转换为 pw.in 文件。GaussView 构建的模型往往 PBC 设置不完善，使用该脚本可以修正并添加周期性边界条件。

---

## 3. pwin2gjf.sh 脚本功能

pwin2gjf.sh 脚本用于将 pw.in 文件转换为 gjf 文件。生成的 gjf 文件中分数坐标部分的晶格矢量显示较为清晰，适合在 GaussView 中使用。

---

## 4. 脚本地址

相关脚本已上传至 GitHub，地址为 https://github.com/FreemanTheMaverick/GVPW.git。

---

## 5. QUANTUM-Espresso 可视化软件局限性

QUANTUM-Espresso 原生自带的 pwgui+ 和 XCrysDen 可视化功能存在不足，如 XCrysDen 在模型较大时可能显示异常或存在 Bug。

---

## 6. BURAI 与 Materials Studio 建模限制

BURAI 适合构建简单模型，但对于复杂模型或 slab 模型添加大真空层的操作效果不佳，通常需要逐个原子拼凑。

---

## 7. 模型转换流程

利用 Materials Studio 等软件构建模型后，可通过脚本将文件转换为 gjf 格式，实现用 GaussView 查看 PWscf 优化轨迹的功能。主要脚本包括 pwin2gjf.sh、pwout2gjf.sh 和 gjf2pwin.sh。

---

## 8. pwin2gjf.sh 使用方法

在当前目录下执行命令 `bash pwin2gjf.sh abc.pw.in`，会生成对应的 abc.pw.gjf 文件，该文件可用 GaussView 打开。

---

## 9. pwin2gjf.sh 注意事项

执行 pwin2gjf.sh 脚本时需注意：必须使用 bash 命令而非 sh；pw 文件中原子坐标单位需为 Angstrom；需确保 pw.in 文件中原子数量正确；转换生成的 gjf 文件使用 Unix 换行符。

---

## 10. pwout2gjf.sh 使用方法

在当前目录下执行命令 `bash pwout2gjf.sh abc.pw.out`，会从 pw 优化输出文件中提取最后一帧结构生成 abc.pw.gjf 文件。

---

## 11. pwout2gjf.sh 功能限制

pwout2gjf.sh 脚本仅转换 pw 优化输出的输出文件，不需要转换静态运行或未优化的输出文件，因为后者可直接使用 pwin2gjf 从输入文件转换。

---

## 12. pwout2gjf.sh 提取逻辑

pwout2gjf.sh 仅转换输出的最后一帧结构，若需读取其他帧数，需要手动修改脚本逻辑。

---

## 13. gjf2pwin.sh 使用方法

在当前目录下执行命令 `bash gjf2pwin.sh abc.pw.gjf settings.pw.in`，会根据 gjf 文件生成 abc.pw.in 输入文件，其中计算参数（如 CONTROL 计算类型、KPOINTS 等）从 settings.pw.in 读取。

---

## 14. gjf2pwin.sh 参数说明

生成的 abc.pw.in 文件中的原子数量取决于 abc.pw.gjf，与 settings.pw.in 无关；abc.pw.gjf 和 settings.pw.in 需位于同一目录。

---

## 15. gjf2pwin.sh 临时文件

运行 gjf2pwin.sh 脚本时会在当前目录下生成临时文件夹 tmp，处理完毕后会自动删除，需注意不要发生文件冲突。

---

## 16. gjf2pwin.sh 脚本用途

gjf2pwin.sh 脚本生成的 pw 输入文件用于作为 GaussView 精细建模的起点，可能需要对晶格平移或对称性进行调整，以适应 pw 计算。

---

## 17. Pt(111)-O2 模型构建流程

使用 MS 或 BURAI 构建 Pt(111) slab 模型；在 BURAI 中导出为 pw 输入文件；修改 pw 输入文件参数；进行 pw 优化得到输出文件；使用 pwout2gjf.sh 将输出文件转换为 gjf 文件并在 GV 中添加分子；使用 gjf2pwin.sh 转换回 pw 输入文件；再次进行 pw 优化并查看结果。

---

## 18. PWscf 输入文件 ibrav 设置

当 PWscf 输入文件中 ibrav 设置为 0 时，程序将从 CELL_PARAMETERS 字段读取晶格矢量。

---

## 19. 坐标与单位要求

涉及周期性边界条件的文件需以 Angstrom 为单位，需确保 ATOMIC_POSITIONS 和 CELL_PARAMETERS 关键词下的数值单位均为 Angstrom。

---

## 20. GaussView 读取 pw.log 单位

GaussView 打开 pw.log 文件时，能量单位显示为 Rydberg，而非 Hartree。

---

## 21. pwout2gauout.sh 性能说明

pwout2gauout.sh 脚本读取 pw.out 文件中所有帧的处理速度较慢，存在等待时间。

---

## 22. 临时文件冲突处理

运行相关脚本时会生成 init_tmp_atom、init_tmp_lat、tmp_atom、tmp_lat 等临时文件，需注意避免与现有同名文件发生冲突。

---

## 23. pwout2gjf.sh 脚本状态

pwout2gjf.sh 脚本已完成并可用。
