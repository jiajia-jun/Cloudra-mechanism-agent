---
key: t29233
title: Docker����, CP2K ȫ�Զ���װ | ��ȫ��� ֻ��ȴ�
url: http://bbs.keinsci.com/thread-29233-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2022
cards: 8
---

# Docker����, CP2K ȫ�Զ���װ | ��ȫ��� ֻ��ȴ� — 知识卡片

## 1. CP2K 官方 Docker 镜像获取

使用官方推荐的方法可直接从 Docker Hub 获取 CP2K 镜像。执行 `docker pull cp2k/cp2k:latest` 可获取 CP2K v10.0-dev 版本，执行 `docker pull cp2k/cp2k:9.1` 可获取 CP2K v9.1 版本。

---

## 2. Docker 安装与学习资源

Docker 的安装及使用需要自行学习相关知识。详细的安装步骤和指南可参考 Docker 官方文档。

---

## 3. 自定义构建 CP2K Docker 镜像

可通过克隆 GitHub 仓库并使用工具目录下的 Dockerfile 自定义构建 CP2K 镜像。首先执行 `git clone --recursive https://github.com/cp2k/cp2k.git cp2k` 克隆代码，随后进入 `cd cp2k/tools/docker` 目录，并执行构建命令。

---

## 4. CP2K Docker 镜像构建命令

构建自定义镜像的命令为 `docker build -f Dockerfile.prod_psmp --build-arg GIT_COMMIT_SHA=$(git rev-parse HEAD) -t cp2k_prod_psmp ../../`。针对不同版本，Dockerfile 的名称可能不同，用户需根据实际情况选择或修改。

---

## 5. CP2K Docker 容器运行示例

运行 CP2K 容器并执行任务的命令示例如下：`docker run --shm-size=1g -ti -v "$(pwd)":/mnt cp2k_prod_psmp mpiexec -genv OMP_NUM_THREADS=2 -np 16 cp2k dbcsr.inp`。此示例中的命令参数仅供参考，实际使用需根据官方文档进行调整。

---

## 6. 运行参数说明与资源配置

示例命令表示启动了 16 个 cp2k.psmp 进程，且每个进程占用 200% CPU。实际应用中需根据具体的输入文件需求、硬件资源情况及性能表现来调整进程数和线程数。

---

## 7. Dockerfile 修改与镜像安全性

若官方 Dockerfile 不满足需求，可直接修改 `cp2k/tools/docker/Dockerfile.prod_psmp` 文件。修改完成后，再次执行 `docker build` 命令即可生成新的镜像，但需注意修改可能带来的安全性问题。

---

## 8. 云服务器构建镜像的性能注意事项

在配置较低的云服务器（如 4c8g 的阿里云/腾讯云 V*S 实例）上构建 Docker 镜像可能会非常耗时且不稳定。如果网络或硬件环境不稳定，不建议在该类云服务器上进行构建操作。
