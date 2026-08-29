---
key: t56056
title: �������co-folding����boltz-2�����ĵ� (2025��9��)
url: http://bbs.keinsci.com/thread-56056-1-1.html
domain: 半经验与构象搜索
source: keinsci
year: 2025
cards: 11
---

# �������co-folding����boltz-2�����ĵ� (2025��9��) — 知识卡片

## 1. Boltz-2 模型简介

Boltz-2 是 MIT 和 Recursion 联合开源的复合物预测模型，可作为 AlphaFold 3 等非开源商业模型的高准确度替代选择。该模型支持基于序列/SMILES 的结构预测、蛋白-蛋白/蛋白-小分子共折叠预测以及小分子筛选。Boltz-2 旨在达到接近 AlphaFold 3 的准确度，同时提供兼具 FEP+ 精度的结合亲和力预测以及用于质量评估的 pTM/iPTM 指标。
- 原文链接: https://boltz.bio/boltz2
- GitHub: https://github.com/jwohlwend/boltz

---

## 2. Boltz-2 资源消耗与硬件需求

Boltz-2 和 RoseTTafold-All Atom 的本地运行对硬件要求较高，通常需要 NVIDIA GPU 及最新的 CUDA 环境支持。初次运行模型参数和数据库下载及解压约需 500-700GB 的存储空间。高硬件门槛使得该工具主要适用于拥有高性能计算资源的研究组进行共折叠或配体筛选任务。

---

## 3. Boltz-2 的 MSA 处理机制

Boltz-2 使用简化的多序列比对 (MSA) 流程，并提供 MSA server 以免去本地下载大型数据库的存储压力。用户可以选择 CPU 或 GPU 模式，使硬件资源有限的研究者也能使用该工具进行预测。若不使用 MSA server，用户也可通过 YAML 配置文件自行提供 MSA 数据或直接进行预测。

---

## 4. Boltz-2 开源协议

Boltz-2 基于 MIT 开源协议发布，允许免费用于学术和商业用途。该模型不设 API Key 限制，提供弹窗式使用条款，但在使用前需阅读相关条款。其开源特性旨在降低高性能结构预测工具的使用门槛。

---

## 5. Boltz-2 安装步骤

安装 Boltz-2 需创建一个新的 Python 3.12 Conda 环境并激活，随后从 GitHub 克隆最新代码库并按照 README 使用 pip 进行安装。安装完成后，可通过命令 `boltz predict --help` 查看使用说明。GitHub 仓库包含最新的版本、文档及预训练模型。

---

## 6. Boltz-2 模型权重与数据缓存

首次运行 Boltz-2 会自动下载并解压约 8GB 的数据到默认缓存目录（通常为 `~/.boltz`），可通过 `--cache` 参数指定路径。在集群安装时需注意节点可能无法直接访问外网，需手动下载 model checkpoint 和 database 文件。选择 Boltz-2 模型时，`--cache` 目录下会生成 3 个权重文件（boltz2_aff.ckpt, boltz2_conf.ckpt, mols.tar）和 1 个包含超过 45,000 个 pkl 文件的 mols/ 目录。下载成功后，后续运行指定同一缓存目录即可复用文件。

---

## 7. Boltz-2 计算性能基准

在官方示例测试中，使用 CPU 运行总耗时约 45 分钟（结构预测 30 分 19 秒 + 亲和力预测 14 分 2 秒），使用 4090 GPU 总耗时约 2 分钟。性能测试显示 GPU 加速效果显著，具体案例可参考 GitHub 中的 examples 目录下的 affinity.yaml 配置文件。

---

## 8. Boltz-2 自定义 MSA 输入问题

在特定测试中，通过 boltz 自动使用 MSA server 进行序列比对未成功，仅测试了输入预先准备好的 MSA（单链）进行预测。YAML 配置文件支持通过 `t` 参数调整使用方式，但在处理特定逻辑或内存限制时可能存在使用限制。早期版本存在自定义 MSA 输入的 Bug，需关注相关 issue 修复。

---

## 9. Boltz-2 当前功能限制

Boltz-2 目前仅支持单链模板输入，不支持 PDB/CIF 格式的多链模板。亲和力预测目前仅支持“蛋白-小分子”体系，且小分子原子数限制为 5 至 128 个。该模型暂不支持针对受体-配体复合物进行单点 Ligand 亲和力预测，若强行输入受体-小分子复合物会报错。此外，该工具暂无针对“多对多”复合物配对预测或基于模板的预测基准，且缺乏可视化的图形用户界面。

---

## 10. AlphaFold 3 使用许可限制

AlphaFold 3 的使用受到严格的法律条款限制，仅允许用于非商业研究用途。用户需遵守 AlphaFold 3 关于训练数据、模型权重、输出文件及源代码的各项许可协议（如 CC-BY-NC-SA）。禁止将 AlphaFold 3 的结果整合入自动化系统（如 AutoDock）用于商业或非授权研究。

---

## 11. AlphaFold 3 相关文献与资源

AlphaFold 3 的核心方法发表于 2024 年的 *Nature* 期刊。相关的使用条款、模型权重使用协议、禁止用途政策及源代码许可协议均可在其 GitHub 仓库查阅。用户在使用前必须详细阅读并同意服务器端权重及输出文件的使用条款。
