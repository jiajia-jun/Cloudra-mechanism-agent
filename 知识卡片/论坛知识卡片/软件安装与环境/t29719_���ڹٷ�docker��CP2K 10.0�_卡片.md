---
key: t29719
title: ���ڹٷ�docker��CP2K 10.0�汾��װ��ʾ
url: http://bbs.keinsci.com/thread-29719-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2022
cards: 10
---

# ���ڹٷ�docker��CP2K 10.0�汾��װ��ʾ — 知识卡片

## 1. CP2K 简介

CP2K 是一款功能强大的开源软件包，适用于固态、液态、分子和生物体系等原子与分子模拟。该软件在计算化学领域具有较好的应用效果。使用 Docker 容器化安装 CP2K 被官方认为是包含所有依赖项的最简单、最方便的方法。

---

## 2. Docker 容器化安装优势

相比于复杂的编译安装步骤，使用 Docker 安装 CP2K 是最简单、最方便且最安全的方法。官方明确指出这是构建 CP2K 及其所有依赖项的最容易方式。通过 Docker 安装的版本通常为 psmp 版本，支持 MPI 和 OpenMP 混合并行。

---

## 3. Docker 软件安装步骤

Docker 的官方安装教程可在 https://docs.docker.com/get-docker/ 查阅。用户也可参考菜鸟教程提供的 Ubuntu 下 Docker 安装指南，链接为 https://www.runoob.com/docker/ubuntu-docker-install.html。Docker 安装成功后，即可进行 CP2K 的后续部署。

---

## 4. CP2K Docker 安装文件获取

CP2K 官方在 GitHub 仓库的 tools/docker 目录下提供了 Dockerfile 文件。对应的 GitHub 链接为 https://github.com/cp2k/cp2k/tree/master/tools/docker。该目录下包含 Dockerfile.prod_psmp 等文件及相关构建命令。

---

## 5. 获取 CP2K 源代码命令

下载最新版 CP2K 源代码的命令为：
`git clone --recursive https://github.com/cp2k/cp2k.git cp2k`
下载指定版本（如 v9.1）CP2K 源代码的命令为：
`git clone --recursive -b support/vx.y https://github.com/cp2k/cp2k.git cp2k`（其中 vx.y 需替换为具体版本号）。
源代码下载完成后，文件大小约为 200 MB。

---

## 6. 进入 Docker 构建目录

下载源代码后，需进入 Docker 构建目录，操作命令为：
`cd cp2k/tools/docker`

---

## 7. 构建 CP2K Docker 镜像

构建 CP2K Docker 镜像的命令为：
`docker build -f Dockerfile.prod_psmp --build-arg GIT_COMMIT_SHA=$(git rev-parse HEAD) -t cp2k_prod_psmp ../../`
构建过程耗时较长，预计需要 1 至 2 小时。

---

## 8. 运行 CP2K 官方测试案例

构建完成后，可进入官方基准测试目录运行测试：
`cd ../../benchmarks/QS_single_node`
运行 dbcsr.inp 测试案例的命令为：
`docker run --shm-size=1g -ti -v "$(pwd)":/mnt cp2k_prod_psmp mpiexec -genv OMP_NUM_THREADS=1 -np 16 cp2k dbcsr.inp`
若测试成功，屏幕将打印输出 "The number of warnings for this run is : 0"。

---

## 9. 使用 Docker 运行自定义计算任务

用户可使用 Docker 运行自定义任务，例如使用 GTH-PBE 基组对 WS2 体系进行计算。运行命令如下：
`docker run --shm-size=1g -ti -v "$(pwd)":/mnt cp2k_prod_psmp mpiexec -genv OMP_NUM_THREADS=1 -np 16 cp2k WS2.inp 1>WS2.out 2>WS2.err`
计算过程中可通过 `top` 命令监控 CP2K 进程数。生成的文件可用于 Multiwfn 等程序进行后续分析，如分析 Molden 文件中的轨道信息。

---

## 10. 计算性能与测试结果

在测试环境中，使用 Docker 运行 CP2K 展示了 16 个线程和 17 个硬件进程的计算性能。测试结果图片通常存储在 test_results 目录中。
