---
key: t19823
title: Rocks Cluster 7.0 Manzanita (CentOS 7.4)ǰ�˽ڵ㰲װ������Ӽ�����ȫ��¼
url: http://bbs.keinsci.com/thread-19823-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2020
cards: 14
---

# Rocks Cluster 7.0 Manzanita (CentOS 7.4)ǰ�˽ڵ㰲װ������Ӽ�����ȫ��¼ — 知识卡片

## 1. Rocks Cluster 7.0 基础信息

Rocks Cluster 7.0 于 2017 年发布，代号为 Manzanita，基于 CentOS 7.4 64 位版本开发。该集群管理系统在安装和使用过程中包含特定的流程与注意事项。

---

## 2. Rocks Cluster 7.0 官方文档地址

Rocks Cluster 7.0 的官方文档位于 http://central-7-0-x86-64.rocksclusters.org/roll-documentation/base/7.0/，该地址提供了相关的基础文档和说明。

---

## 3. 前端节点安装介质要求

前端节点（Frontend，即管理节点）的文件安装通常需要通过 Kernel Roll CD 完成，也支持使用 USB 进行安装。Rocks 7 支持网络安装，但前提是必须先进行详细研究和准备。

---

## 4. 前端节点网络访问要求

进行网络安装时，必须确保网络中存在前端节点可以访问的 HTTP 服务器，该服务器需包含所需的安装文件资源。

---

## 5. Web 服务器软件建议

官方用户指南中建议使用 Apache 提供 HTTP 服务。关于使用 Nginx 是否存在问题，原文未给出明确结论。

---

## 6. 下载文件校验

下载完成后，推荐对压缩包进行 MD5 校验。官方提供的 MD5 校验值文件位于 http://central-7-0-x86-64.rocksclusters.org/isos/md5sums.txt，按照官方提示进行校验可验证文件完整性。

---

## 7. 自定义安装构建细节

进行自定义安装构建时，相关文件可能需要按特定的指定格式列出。具体的构建格式和要求可以参考 https://github.com/rocksclusters/roll-server。

---

## 8. index.cgi 脚本 Python 版本支持

安装过程中涉及的 index.cgi 脚本使用 Python 2.X 编写，不支持 Python 3.X。

---

## 9. 安装顺序与耗时

安装过程需要按照特定的依赖顺序执行。如果遵循正确的安装顺序，整个安装过程大约需要 30 分钟左右。

---

## 10. 集群配置名称设置

在安装配置阶段，需要在 CLUSTER CONFIG 中的 Cluster Name 处填写集群名称。填写完成后需按回车键确认，以确保设置成功。

---

## 11. 计算节点安装触发方式

前端节点安装完成后，移除 CD 或 USB 启动介质即可进行计算节点的安装。此时需以 root 账户登录前端节点，并输入命令 "insert-ethers"。

---

## 12. 计算节点类型选择

执行 "insert-ethers" 命令后，在 Appliance Type 选项中选择 "compute"，即可开始计算节点的部署流程。

---

## 13. 前端与计算节点硬件连接要求

前端节点与计算节点之间必须通过千兆交换机连接到同一个物理以太网络中。若网络连接不符合此要求，节点之间将无法进行正常通讯。

---

## 14. 计算节点自动安装机制

计算节点支持开机自动安装功能（如支持 PXE 启动）。启动后需等待一段时间，前端节点会将用户信息同步完成，从而实现计算节点的自动配置。
