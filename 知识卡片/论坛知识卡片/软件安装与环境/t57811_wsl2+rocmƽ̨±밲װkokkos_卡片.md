---
key: t57811
title: wsl2+rocmƽ̨�±��밲װkokkos���ٵ�lammps
url: http://bbs.keinsci.com/thread-57811-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2026
cards: 14
---

# wsl2+rocmƽ̨�±��밲װkokkos���ٵ�lammps — 知识卡片

## 1. WSL2与ROCm硬件环境

该安装过程基于AMD处理器和显卡在WSL2环境下的验证。硬件配置为AMD 9700X CPU搭配AMD Radeon RX 7900 GRE显卡。操作系统版本为WSL2中的Ubuntu 22.04。

---

## 2. ROCm安装与验证

ROCm软件栈在WSL2中通过amdgpu-install工具进行安装。安装完成后，运行rocminfo命令可以检测GPU是否被正确识别。

---

## 3. ROCm安装命令示例

使用wget下载指定版本的amdgpu-install安装包并执行安装。命令参数包含`--usecase=wsl,rocm --no-dkms`以适配WSL环境。

---

## 4. AMD GPU信息识别

rocminfo命令的输出中包含了显卡的详细架构信息。对于AMD Radeon RX 7900 GRE，其架构名称（Name）识别为gfx1100。

---

## 5. LAMMPS编译依赖

编译LAMMPS前需安装基础编译工具链。必要的依赖包包括gcc、gfortran、build-essential、cmake和make。

---

## 6. LAMMPS源码获取

从LAMMPS官方网站下载stable版本的源码压缩包。使用tar命令解压后进入lammps源码目录。

---

## 7. LAMMPS安装包配置

编译前需修改`cmake/presets/basic.cmake`文件以启用所需的LAMMPS软件包。配置中包含了GPU、Kokkos及其他多种计算和物理模型包。

---

## 8. Kokkos显卡架构配置

针对AMD显卡，需修改`cmake/presets/kokkos-hip.cmake`文件中的架构设置。将gfx1100架构对应的选项`Kokkos_ARCH_NAVI1100`设置为ON。

---

## 9. LAMMPS CMake编译配置

创建build目录并执行cmake命令进行配置。关键参数包括指定ROCm路径、使用hipcc编译器、设置GPU_API为HIP及HIP_ARCH为gfx1100。

---

## 10. LAMMPS编译构建

执行`cmake --build . -j16`命令开始编译LAMMPS。编译过程中启用了PKG_GPU和PKG_KOKKOS选项以支持GPU加速。

---

## 11. WSL2运行时路径注意事项

在WSL2环境下进行AI计算或相关任务时，需注意ROCm runtime路径的稳定性。若路径发生变更，可能需要重新编译LAMMPS以避免运行报错。

---

## 12. LAMMPS GPU加速测试

使用LAMMPS自带的bench目录下的in.eam输入文件进行性能测试。执行命令中需包含`-k on g 1 -sf kk`参数以开启Kokkos GPU加速。

---

## 13. AMD 7900 GRE测试性能

在AMD Radeon RX 7900 GRE上运行基准测试的性能输出为104.278 ns/day。测试结果显示每步计算耗时0.230小时，即每秒241.385步。

---

## 14. 与NVIDIA 3090性能对比

对比数据显示，NVIDIA RTX 3090的测试性能为776.628 ns/day。AMD 7900 GRE在该测试下的速度约为RTX 3090的13.4%。
