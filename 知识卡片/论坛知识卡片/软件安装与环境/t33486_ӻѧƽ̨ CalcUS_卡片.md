---
key: t33486
title: ��������ӻ�ѧƽ̨ CalcUS
url: http://bbs.keinsci.com/thread-33486-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2022
cards: 18
---

# ��������ӻ�ѧƽ̨ CalcUS — 知识卡片

## 1. CalcUS 项目简介

CalcUS 是一个基于 Web 的计算化学平台，源自 GitHub 项目 cyllab/CalcUS。该平台支持提交计算任务并通过 Web 界面进行可视化展示，适用于 Gaussian 16、ORCA、xtb 等计算软件。项目代码开源，用户可以根据需求进行修改和部署。

---

## 2. 推荐终端工具 MobaXterm

MobaXterm 是一款全功能终端软件，支持 SSH、SFTP 和 X11 转发。在维护 Linux 服务器或进行远程计算管理时，该工具是推荐的辅助工具。其下载地址为 https://mobaxterm.mobatek.net/download-home-edition.html。

---

## 3. Docker 的安装与更新

在 Ubuntu 系统上安装 Docker 前，建议先更新软件源和系统包。可以使用 `sudo apt-get update` 和 `sudo apt upgrade -y` 命令进行更新，随后使用 `sudo apt install docker -y` 或 `sudo apt install docker.io -y` 安装 Docker。

---

## 4. Docker Compose 的安装

Docker Compose 可通过 curl 命令从 DaoCloud 镜像源下载特定版本（1.27.3）。安装命令为 `sudo curl -L "https://get.daocloud.io/docker/compose/releases/download/1.27.3/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose`。下载后需使用 `sudo chmod +x /usr/local/bin/docker-compose` 赋予执行权限。

---

## 5. Docker 用户组权限配置

为了避免每次使用 Docker 都需要 sudo 权限，建议将当前用户添加到 docker 用户组。操作步骤包括创建组 `sudo groupadd docker`、添加用户 `sudo usermod -aG docker $USER` 以及刷新组信息 `newgrp docker`。

---

## 6. CalcUS 部署包准备

由于原项目可能存在缺失或报错，建议使用经过修改的 CalcUS 部署包。该包可从 123 网盘、OneDrive 或天翼云盘下载。下载完成后需将压缩包移动到用户主目录（$HOME）下。

---

## 7. CalcUS 的安装与启动

将下载的 `calcus.tar.gz` 在主目录解压后，会生成 CalcUS 文件夹。进入该文件夹并执行 `bash start.sh` 脚本即可启动服务。启动过程会自动拉取 Docker 镜像，当终端显示 web_1 容器落下时表示启动成功。

---

## 8. CalcUS 默认登录信息

CalcUS 服务启动后，可通过浏览器访问 `IP:1234` 进入登录页面。系统默认的登录账号为 `wxyhgk`，默认密码为 `default`。

---

## 9. CalcUS 账号密码重置

如需修改默认账号和密码，需删除 CalcUS 目录下的 `.env` 文件并运行 `python3 generate_env.py` 重新生成配置文件。该脚本会创建新的 `.env` 文件并提示用户设置新的用户名和密码。配置完成后需重新运行 `bash start.sh`。

---

## 10. CalcUS 服务的后续启动与停止

首次启动后，后续开启服务可直接在 CalcUS 目录下运行 `docker-compose start`。停止服务可在终端中按 `Ctrl + c`。再次执行 `bash start.sh` 会删除并重建旧的 Docker 容器。

---

## 11. 集群环境软件要求

若要使用 CalcUS 管理集群计算任务，需要在远程计算节点上安装 Slurm 作业调度系统。此外，集群节点还需预先安装并配置好 Gaussian 16、ORCA、xtb、crest 等计算软件。

---

## 12. 集群计算软件目录配置

在集群用户主目录下创建 `calcus` 目录，并将 Gaussian 16、ORCA、xtb 等软件安装包放入该目录。软件应解压在此目录下，以便后续提交脚本调用。

---

## 13. Gaussian 16 集群提交脚本配置

Gaussian 16 的提交脚本需设置 Slurm 参数，包括作业名、分区、核心数（如 -n 8）及输出文件名。环境变量部分需设置 `g16root`、`GAUSS_SCRDIR` 并加载 g16.profile 路径。脚本最后需切换至提交目录 `cd $SLURM_SUBMIT_DIR`。

---

## 14. ORCA 集群提交脚本配置

ORCA 的提交脚本需配置 OpenMPI 环境变量以及 ORCA 的安装路径（如 `EBROOTORCA` 和 PATH）。Slurm 参数需指定任务数（如 -n 32）和每节点任务数。邮件通知地址和分区名称需根据实际情况修改。

---

## 15. xtb 集群提交脚本配置

xtb 的提交脚本需设置 `XTBPATH` 和 xtb 的 bin 路径至环境变量 PATH 中。需配置 `OMP_NUM_THREADS` 和 `MKL_NUM_THREADS` 线程数，并设置 `ulimit -s unlimited`。邮件通知和分区配置需替换为实际信息。

---

## 16. CalcUS 集群连接设置

在 CalcUS 网页端点击右上角 "My Profile" 可进入集群设置界面。需填写 Cluster Address（远程服务器 SSH IP:端口）、Cluster Username（远程用户名）、Core per Calculation（核心数）和 Memory per Calculation（内存）。

---

## 17. CalcUS 集群 SSH 密钥配置

在集群设置界面点击 "View public key" 可获取公钥。将此公钥添加到远程服务器的 `~/.ssh/authorized_keys` 中，配置免密 SSH 登录。配置完成后点击 "Connect to cluster" 按钮即可测试连接。

---

## 18. CalcUS 任务提交与监控

完成集群连接配置后，即可在 CalcUS 界面创建并提交计算任务。平台支持对任务进行可视化管理。详细的项目文档和功能说明可参考 CalcUS 官方文档。
