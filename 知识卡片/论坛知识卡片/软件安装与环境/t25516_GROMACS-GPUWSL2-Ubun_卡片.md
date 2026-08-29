---
key: t25516
title: GROMACS-GPU����WSL2-Ubuntu�еİ�װ����
url: http://bbs.keinsci.com/thread-25516-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2021
cards: 16
---

# GROMACS-GPU����WSL2-Ubuntu�еİ�װ���� — 知识卡片

## 1. NVIDIA 对 WSL 环境的 GPU 驱动支持

目前 NVIDIA 仅提供 WSL-Ubuntu 环境下的 GPU 驱动支持，虚拟机环境无法使用此方案。在 WSL2 中利用 GPU 进行计算时，只需在 Windows 主机安装支持 WSL 的驱动即可，无需在 Linux 内部安装驱动。

---

## 2. Windows 下安装 CUDA on WSL 的注意事项

安装 CUDA on WSL 前，用户建议勾选静默安装以减少不必要的问题。若安装过程中遇到问题，可使用 DDU 工具彻底卸载旧版驱动并删除残留文件。

---

## 3. WSL2 中查看 GPU 状态

在 Windows 已安装 CUDA for WSL 的前提下，于 Linux 环境下使用 root 用户执行 `nvidia-smi` 命令即可查看 GPU 状态。若当前非 root 用户，需先执行 `su` 命令切换至 root 用户或使用 sudo 权限。

---

## 4. WSL2 中的软件下载与安装目录建议

为便于管理，建议在用户目录下新建文件夹（如 `softPackage`）存放安装包，使用 wget 或 git 下载时进入该目录执行命令。使用 root 用户安装软件时，建议指定安装路径为 `/usr/local/xxx`，以便其他用户共同使用。

---

## 5. WSL-Ubuntu 下安装 CUDA Toolkit (方法一)

在 WSL-Ubuntu 下安装 CUDA Toolkit 11.4，可通过下载并配置 pin 文件、repo 包、添加 key 及更新源来完成。安装命令序列包括 `sudo dpkg -i`、`sudo apt-key add`、`sudo apt-get update` 及 `sudo apt-get -y install cuda`。

---

## 6. Ubuntu 下单独安装 CUDA Toolkit (方法二)

在 Ubuntu 20.04 下可单独安装 `cuda-toolkit-11-4`，方法为配置 ubuntu2004 的 pin 文件与 repo 包后，执行 `sudo apt-get install -y cuda-toolkit-11-4`。此方法与常规 Linux 安装 CUDA 类似，需注意在安装选项中选择 toolkit 及指定版本。

---

## 7. CUDA 环境变量配置

安装完成后需修改 `.bashrc` 文件添加环境变量，包括 `export PATH=$PATH:/usr/local/cuda-11.4/bin` 和 `export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/cuda-11.4/lib64`。配置完成后重启终端，使用 `nvcc --version` 命令可查看 CUDA Toolkit 版本。

---

## 8. CUDA 不同版本的安装命令获取

不同版本的 CUDA 安装命令可在 NVIDIA 搜索页面或对应版本的下载归档页面（如 11.1.0 至 11.6.0）中查询。对于 WSL-Ubuntu，下载选项需选择 linux - x86_64 - WSL-Ubuntu - 2.0 - deb(local)；对于常规 Ubuntu，需选择 linux - x86_64 - Ubuntu - 18.04/20.04 - deb(local)。

---

## 9. 多版本 CUDA 共存与调用

不同版本的 CUDA 可以共存，通过在 `.bashrc` 中修改 PATH 路径进行切换。软链接 `/usr/local/cuda` 及 `/usr/local/cuda-11` 默认指向最新安装的 CUDA 版本，若需使用特定版本（如 11.4），应使用实际安装文件名（如 `/usr/local/cuda-11.4`）。

---

## 10. WSL2 下安装 Gromacs 的版本选择

在 WSL2 下安装 Gromacs 需注意版本兼容性，2020.x 之前版本无法正确识别 WSL 下的 GPU 设备，推荐使用 2020.6 版本或更高版本（如与 Ubuntu 20.04 同步版本）。

---

## 11. Gromacs 编译的依赖与配置要求

编译 2021.x 及以上版本的 Gromacs 建议使用较高版本的 CMake（apt 默认安装的 3.13 版本可能较旧）。编译参数中 `-DCMAKE_INSTALL_PREFIX` 指定 Gromacs 安装路径，`-DGMX_GPU=ON` 开启 GPU 支持，`-DCUDA_TOOLKIT_ROOT_DIR` 指定 CUDA Toolkit 安装路径（默认为 `/usr/local/` 下对应目录）。

---

## 12. 编译 Gromacs 的排错建议

在编译过程中如果出现报错中止，建议查看报错信息并修正，在下次执行 `make` 前先执行 `make clean` 清理。

---

## 13. 安装 CMake

CMake 可直接通过 apt 命令安装，默认安装路径通常为 `/usr/bin`。

---

## 14. 编译安装 FFTW

编译安装 FFTW 3.3.8 时，可使用 `./configure --prefix=/usr/local/fftw338 --enable-sse2 --enable-avx --enable-float --enable-shared --enable-avx2` 配置安装路径及开启相关指令集支持。随后执行 `make install -j` 完成安装，并在 `.bashrc` 中添加对应的 PATH 和 LD_LIBRARY_PATH 环境变量。

---

## 15. 编译安装 Gromacs

在解压 Gromacs 源码并创建 build 目录后，需设置 `CMAKE_PREFIX_PATH` 为 FFTW 安装路径，并执行 cmake 命令指定安装前缀、开启 RDTSCP 和 GPU 支持及设置 CUDA 路径。具体命令为 `cmake .. -DCMAKE_INSTALL_PREFIX=/usr/local/gmx2020.6 -DGMX_USE_RDTSCP=ON -DGMX_GPU=ON -DCUDA_TOOLKIT_ROOT_DIR=/usr/local/cuda-11.4`，随后执行 `make -j`、`make check` 和 `make install`。

---

## 16. Gromacs 环境变量激活

安装完成后需在 `.bashrc` 中添加 `source /usr/local/gmx2020.6/bin/GMXRC` 以激活 Gromacs 环境变量。重启终端后执行 `gmx --version` 可验证安装版本。
