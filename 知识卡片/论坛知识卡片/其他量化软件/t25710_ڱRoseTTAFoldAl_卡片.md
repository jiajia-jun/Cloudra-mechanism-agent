---
key: t25710
title: �ڱ�������RoseTTAFold��AlphaFold2
url: http://bbs.keinsci.com/thread-25710-1-1.html
domain: 其他量化软件
source: keinsci
year: 2021
cards: 21
---

# �ڱ�������RoseTTAFold��AlphaFold2 — 知识卡片

## 1. RoseTTAFold 与 AlphaFold2 的硬件需求

RTX 2080ti 显卡可用于运行 RoseTTAFold 和 AlphaFold2，但显存较小的显卡可能在运算过程中发生显存溢出。V100 或 A100 显卡（10GB 以上）能提供更稳定的显存支持。无本地 GPU 环境可使用基于 Google Colab 的 ColabFold 进行结构预测。

---

## 2. 无 GPU 环境的替代方案

ColabFold 是适合无 GPU 环境用户的结构预测工具，它利用谷歌的云端资源快速进行预测并允许添加多种自定义模版。相关操作演示可参考 Bilibili 视频资源 (https://www.bilibili.com/video/BV1Yg411L7Sh)。

---

## 3. RoseTTAFold 安装前的环境准备

安装前需配置 GPU 驱动及 CUDA 环境，官方推荐使用 cuda 11 版本，使用 cuda 10 也可运行。

---

## 4. RoseTTAFold 的原理与背景

RoseTTAFold 由华盛顿大学 David Baker 团队开发，是受 AlphaFold2 在 CASP14 成功启发后推出的 3-track 神经网络。该网络整合了一维序列（MSA）、二维接触图和三维结构信息，以实现高精度的结构预测。

---

## 5. RoseTTAFold 源码下载

通过 git 命令克隆 RoseTTAFold 仓库：
git clone git@github.com:RosettaCommons/RoseTTAFold.git

---

## 6. RoseTTAFold 构建序列 MSA 所需数据库

构建 MSA 需下载 Uniref30 数据库：
http://wwwuser.gwdg.de/~compbiol/uniclust/2020_06/UniRef30_2020_06_hhsuite.tar.gz

---

## 7. RoseTTAFold 所需 BFD 数据库

RoseTTAFold 运行需要下载 BFD 数据库：
https://bfd.mmseqs.com/bfd_metaclust_clu_complete_id30_c90_final_seq.sorted_opt.tar.gz

---

## 8. RoseTTAFold 结构模版数据库

结构模版数据库下载地址：
https://files.ipd.uw.edu/pub/RoseTTAFold/pdb100_2021Mar03.tar.gz

---

## 9. RoseTTAFold 预训练权重文件

RoseTTAFold 的预训练权重文件下载命令：
wget https://files.ipd.uw.edu/pub/RoseTTAFold/weights.tar.gz

---

## 10. RoseTTAFold 依赖安装与脚本使用

运行 `./install_dependencies.sh` 脚本可快速安装必要的编译及外部程序。若需手动指定工具路径，可修改 scripts 目录下的脚本。

---

## 11. RoseTTAFold 结构预测运行命令

进行结构预测时，运行命令格式为：`../run_[pyrosetta, e2e]_ver.sh input.fa`。其中 pyrosetta 版本和 e2e 版本为两种不同的运行模式。

---

## 12. RoseTTAFold 复合物建模

RoseTTAFold 支持蛋白复合物建模，相关操作说明位于 `example/complex_modeling/README` 文件中。该流程通常先生成 MSA 再进行预测。

---

## 13. AlphaFold2 的背景与性能

AlphaFold2 由 Google DeepMind 团队开发，在 CASP14 竞赛中表现优异，多数目标蛋白的结构预测结果达到了 tmscore>90 的精度，被视为接近实验测定精度的突破性工具。

---

## 14. AlphaFold2 源码下载

通过 git 命令克隆 AlphaFold2 仓库：
git@github.com:deepmind/alphafold.git

---

## 15. AlphaFold2 MSA 数据库准备

AlphaFold2 所需的 BFD 数据库与 RoseTTAFold 相同，具体下载及更新操作位于 scripts 文件夹的脚本中。

---

## 16. AlphaFold2 Conda 环境配置步骤

创建并激活名为 af2 的 conda 虚拟环境的命令如下：
conda create -n af2 python=3.8
conda activate af2

---

## 17. AlphaFold2 Python 依赖安装

安装基础 Python 依赖包：
pip install -r requirements.txt

---

## 18. AlphaFold2 与 Jax 的版本对应

TensorFlow-gpu 版本需与 CUDA 版本对应：cuda 101 对应 2.3.0，cuda 110 对应 2.5.0，cuda 100 对应 2.0.0。Jax 安装示例如下（针对 cuda 101）：
pip install --upgrade jax==0.2.14 jaxlib==0.1.69+cuda101 -f https://storage.googleapis.com/jax-releases/jax_releases.html

---

## 19. AlphaFold2 额外工具与补丁

使用 conda 安装 pdbfixer 并安装 mock：
conda install -c omnia pdbfixer
pip install mock
非 Docker 安装方式可能需要应用几个补丁，详情参考 https://github.com/kalininalab/alphafold_non_docker。

---

## 20. ColabFold 的 MSA 生成优势

使用 ColabFold 进行 MSA 生成比本地运行耗时更短，它内置了 mmseq2 的加速流程。该流程无需下载大型数据库，直接调用网络 API 即可快速获得高质量的 MSA 结果。

---

## 21. 本地部署 ColabFold

除使用在线 Colab 外，也可以参考 localcolabfold 仓库在本地部署 ColabFold：
https://github.com/YoshitakaMo/localcolabfold
