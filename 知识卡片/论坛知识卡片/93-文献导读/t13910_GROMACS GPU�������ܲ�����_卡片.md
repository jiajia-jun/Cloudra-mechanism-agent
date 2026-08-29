---
key: t13910
title: GROMACS GPU�������ܲ�������(JCC,2019)
url: http://bbs.keinsci.com/thread-13910-1-1.html
domain: 93-文献导读
source: keinsci
year: 2019
cards: 4
---

# GROMACS GPU�������ܲ�������(JCC,2019) — 知识卡片

## 1. GROMACS GPU 性能测试文献参考

Journal of Computational Chemistry 于 2015 年发表了一篇关于 GROMACS GPU 性能的详细测试文章。2019 年上传的文档《More Bang for Your Buck-Improved use of GPU Nodes for GROMACS 2018》针对更新的 GPU 和新版 GROMACS 进行了补充测试。
- 原文出处：Journal of Computational Chemistry 2015, 36, 1990–2008
- 补充文档：More Bang for Your Buck-Improved use of GPU Nodes for GROMACS 2018.pdf

---

## 2. RTX2080 搭配低配 CPU 的性价比

根据测试结果，将 RTX2080 搭配低档 CPU 或高配 GPU 均可达到较高的性价比和良好的性能。目前主流服务器已经出现了配备高端 GPU 但 CPU 性能一般的配置，在这种情况下提高 CPU 配置对提升性能作用有限。
- 适用硬件：RTX2080, RTX2060, GTX10x0 系列
- 建议：若已有 RTX2060，升级至 2080 的性能提升可能不明显；GTX10x0 系列可暂不考虑升级

---

## 3. 多 GPU 节点的配置策略

在大型机或集群模式下，使用十几到二十个低配 CPU 核心搭配多个 GPU 是性价比很高的选择。
- 适用场景：大型机、集群
- 推荐比例：十几至二十个低配 CPU 核心对应多个 GPU

---

## 4. GROMACS 2018 PME 负载转移

GROMACS 从 2018 版本开始，PME（Particle Mesh Ewald）的倒易空间部分可以转移到 GPU 上进行计算。这一改动减轻了 CPU 的计算负担，使得性能瓶颈更多转向 GPU，与之前版本有所不同。
- 涉及功能：PME 倒易空间计算
- 版本变更：GROMACS 2018 及以后
