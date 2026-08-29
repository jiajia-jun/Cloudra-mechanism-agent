---
key: t30907
title: CP2K-singularity�������
url: http://bbs.keinsci.com/thread-30907-1-1.html
domain: 资源发布与站务
source: keinsci
year: 2022
cards: 4
---

# CP2K-singularity������� — 知识卡片

## 1. CP2K AVX2 版本编译资源

2023年7月12日更新了AVX2版本的编译文件，涵盖7.1至2023.1版本。该版本针对使用AVX2指令集的CPU进行了优化，支持点电荷、偶极子等相互作用，不适用于AVX512架构的处理器。
- 资源下载链接为 https://pan.quark.cn/s/64aa03464903，提取码为 Hh7Y。
- 在支持AVX2的硬件上运行此版本，计算速度可提升约5倍。

---

## 2. AVX2与AVX512版本性能对比

全AVX2版本的CP2K在支持AVX2的CPU上运行稳定。在支持AVX512的CPU上使用AVX2版本通常不会出现错误，但无法发挥硬件的最大性能优势。
- 相较于8.1版本，新版AVX2版本速度提升不明显，因此实际应用中推荐使用8.1版本以获得更好的计算效率。

---

## 3. CP2K编译方法参考

CP2K的编译和使用方法可参考特定的教程文档。该教程详细介绍了编译步骤、参数设置及相关配置。
- 参考链接为 http://bbs.keinsci.com/thread-25773-1-1.html。

---

## 4. CP2K官方Docker镜像获取

CP2K官方已在Docker Hub上上传了镜像文件，用户可以直接使用pull命令拉取。通过Docker容器运行CP2K，可以避免复杂的本地编译过程，且环境配置通常基于官方推荐的标准。
- Docker镜像地址为 https://hub.docker.com/r/cp2k/cp2k/tags。
- 提取码为 ThyJ。
