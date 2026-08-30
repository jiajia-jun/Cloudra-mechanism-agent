---
key: t34456
title: �� openMolcas ��������� Hessian ����
url: http://bbs.keinsci.com/thread-34456-1-1.html
domain: 其他量化软件
source: keinsci
year: 2022
cards: 7
---

# �� openMolcas ��������� Hessian ���� — 知识卡片

## 1. openMolcas 参考系原点设置

在分子动力学或结构优化计算中需明确参考系原点，Gaussian 与 Molpro 均设有默认参考系，而 openMolcas 需手动在输入文件中进行设置。
- 使用 openMolcas 时若不明确指定参考系原点，可能会导致计算错误或结果偏差。

---

## 2. 检查 Hessian 矩阵的输入模块

计算流程中需确认 Hessian 矩阵，并在输入文件中添加特定模块以调用相关功能。
- 输入参数包括 `&MCKINLEY`、`perturbation`、`hessian`、`showhessian`。

---

## 3. Hessian 矩阵输出格式与维度

执行计算后程序会输出一个 $3N \times 3N$ 的 Hessian 矩阵（$N$ 为原子数），该矩阵包含体系振动频率与力的相关信息。
- 输出格式适合通过脚本进行后续读取与分析。

---

## 4. 从 Molpro 转向 openMolcas 的效率优势

相较于 Molpro，openMolcas 在处理参考系相关计算时速度较快，具有明显的计算效率优势。
- 建议将相关计算项目迁移至 openMolcas 以提升效率。

---

## 5. Hessian 矩阵准确性与频率验证

若计算得到的频率与 Gaussian 的结果存在差异（例如误差超过 0.1 cm⁻¹），则表明 Hessian 矩阵可能不准确。
- Hessian 矩阵的准确性直接决定了频率计算的可靠性。

---

## 6. 输出 Hessian 矩阵的代码修改位置

openMolcas 源码中负责输出 Hessian 矩阵的逻辑位于 `src/mclr/output_mclr.f` 文件第 530 行附近。
- 通过修改源码可在调用 `FreqAnal` 之前输出实 Hessian 矩阵数据。

---

## 7. 输出 Hessian 矩阵的 Fortran 代码

在源码中添加打印语句可将 Hessian 矩阵数值直接输出到标准输出或日志文件中。
- 具体代码为 `write(6,*) 'Real Hessian by wb'` 和 `write(6,'(3E18.10)') Hess`。
