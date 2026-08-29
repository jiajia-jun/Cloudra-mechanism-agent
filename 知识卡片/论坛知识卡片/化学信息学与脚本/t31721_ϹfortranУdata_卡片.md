---
key: t31721
title: �Ϲ�fortran�����У���data�����鸳ֵ�Ŀ�
url: http://bbs.keinsci.com/thread-31721-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2022
cards: 4
---

# �Ϲ�fortran�����У���data�����鸳ֵ�Ŀ� — 知识卡片

## 1. Fortran DATA语句在子程序中的赋值机制

在多个子程序中使用 `DATA` 语句对同一个 `COMMON` 块中的不同变量分别进行赋值时，不同编译器表现出不同的行为。
- `ifort` 编译器能够按预期分别初始化各个子程序中的变量。
- `gfortran` 编译器可能只识别最后一个被调用的子程序中的 `DATA` 赋值，导致其他变量保持为初始值（如0）。

---

## 2. gfortran对COMMON块DATA语句的处理限制

`gfortran` 对于位于同一个 `COMMON` 块中的数组变量，仅允许在同一个子程序或 `BLOCK DATA` 程序单元中使用 `DATA` 语句进行赋值。
- 如果将赋值操作分散在不同的子程序中，`gfortran` 可能无法正确执行所有初始化。
- 解决方案包括将所有初始化集中在同一位置，或使用直接赋值的可执行语句。

---

## 3. 解决gfortran初始化问题的替代方案

为了解决 `gfortran` 在处理分散 `DATA` 语句时的潜在问题，可以将 `subroutine` 替换为 `BLOCK DATA` 并删除主程序中的 `CALL` 语句。
- 此操作会导致 `gfortran` 仅保留最后编译的 `BLOCK DATA` 中的赋值效果。
- 另一种推荐的解决方法是将 `COMMON` 块拆分，使不同数组位于不同的命名公用块中（如 `/common1/` 和 `/common2/`）。

---

## 4. Fortran DATA语句的重复赋值规则

对同一个变量使用多条 `DATA` 语句进行重复赋值时，标准规定只有最后一次赋值生效。
- 初始化时若先将数组全设为1.0，随后又将第二个元素赋值为-2.0，最终结果是第二个元素变为-2.0，其余保持1.0。
- `ifort` 和 `gfortran` 均遵循此规则，这与部分早期或特定编译器（如 MS-V. Fortran）可能表现出的多次赋值累加行为不同。
