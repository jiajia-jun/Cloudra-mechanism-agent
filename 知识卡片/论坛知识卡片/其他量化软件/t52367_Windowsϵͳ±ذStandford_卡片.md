---
key: t52367
title: Windowsϵͳ�±��ذ�Standford Storm���ñʼ�
url: http://bbs.keinsci.com/thread-52367-1-1.html
domain: 其他量化软件
source: keinsci
year: 2025
cards: 19
---

# Windowsϵͳ�±��ذ�Standford Storm���ñʼ� — 知识卡片

## 1. Stanford Storm 工具概述

Stanford Storm 是一个基于大语言模型的开源知识库生成工具，通过模拟多位“专家”进行视角发散、话题探讨和综述总结以自动生成带参考文献的报告。该工具支持使用 Google Account 登录或直接从 GitHub 下载源码在本地部署，用户可根据网络环境选择访问方式。

---

## 2. 本地部署环境配置

在 Windows 10 系统（如 Microsoft Surface Pro 7, 16GB RAM, Intel i7 CPU）上，需安装 Miniconda3 (64-bit) 并使用 Anaconda PowerShell prompt 创建环境。PyTorch 配置为 CPU 版本，源码基于 GitHub 2025年1月22日及以后的版本（测试时间截至2025年3月23日）。

---

## 3. 安装 knowledge storm 模块

通过 `git clone` 下载源码后，在 storm 目录下按照 README 文件指示创建 conda environment 并激活，运行 `pip install -r requirements.txt`。搜索引擎 API 推荐使用 Tavily (需注册 login，免费计划每月1000 credits)，安装命令为 `pip install tavily-python`。

---

## 4. 配置 API 密钥文件

在项目目录下创建 `secret.toml` 文件，填入 API key 和 LLM server 地址。若使用学校提供的 GPT (Microsoft Azure)，需设置 `OPENAI_API_TYPE="azure"` 和 `AZURE_OPENAI_ENDPOINT="学校提供的API endpoint地址"`，同时设置 `TAVILY_API_KEY="个人的tavily API key"`。

---

## 5. 修改脚本适配 Azure 接口

在 `examples/storm_examples/run_storm_wiki_gpt.py` 脚本中修改 model name，并将 `openai_kwargs["api_base"] = os.getenv("AZURE_API_BASE")` 改为 `openai_kwargs["azure_endpoint"] = os.getenv("AZURE_OPENAI_ENDPOINT")`。不同服务提供商的参数可能不同，具体配置需参考 error message 提示调整。

---

## 6. 安装轻量级 Demo GUI

进入 `.\frontend\demo_light` 目录，按 README.md 指示运行 `pip install -r requirements.txt` 安装 GUI 所需依赖。安装源码后需在 `demo_util.py` 中取消注释 `import sys` 和 `sys.path.append('../..')` 以修复路径。

---

## 7. 运行命令行生成任务

返回 storm 项目主目录，确认 API KEY 配置无误后，执行命令 `python run_storm_wiki_gpt.py --output_dir ".\frontend\demo_light\DEMO_WORKING_DIR" --do-research --do-generate-outline --do-generate-article --do-polish-article --remove-duplicate --retriever tavily`。命令中必须指定输出目录为 GUI 对应的工作目录。

---

## 8. 设定生成主题

运行时输入 Topic，应避免使用下划线，建议使用短横线连接单词（如“Topic: 一种基于机器学习的势函数面”应改为“Topic: machine-learning-based-potential-energy-surface”）。Topic 长度不宜过长，否则可能触发自动截断或影响实际使用效果。

---

## 9. 启动 Demo GUI 界面

进入 `frontend\demo_light` 目录，确认命令行步骤生成的文件已存在于 `DEMO_WORKING_DIR` 中，运行 `streamlit run storm.py`。首次启动可能会出现防火墙提示，需要允许访问。

---

## 10. GUI 界面操作功能

在 GUI 界面点击“New Article”创建新文章，或在“My Articles”路径下查找已生成的文章。选择具体 Article 后，通过 scroll down 点击“Click here to view the agent's brainSTORMing process!”可查看“专家”agents 的讨论过程数据。

---

## 11. 搜索引擎与服务器选择

DuckDuckGo API 虽免费但容易遇到 rate limit，Google Search API 需配置 Google Account 并处理直连问题。若不想处理本地安装的配置问题，或者遇到 CoStorm 功能报错（如 page not found），建议直接使用 Stanford Storm 的官方 server。

---

## 12. 生成文本的质量与局限性

生成的文本在综述和研究深度上表现良好，适合在 deadline 前快速获取 big picture 或辅助撰写专题报告。但在具体数据细节上可能出现错误（如混淆概念或遗漏关键词），不能完全替代人工核对，生成的“参考文献”可能包含虚假链接需谨慎引用。

---

## 13. 文本润色与格式建议

生成的文章虽已 polish，但仍需进行人工润色以修正文风。建议检查 Markdown 格式中的缩写（Abbreviations），确保首次出现时使用全称，全文应保持术语风格统一（如 report 和 article 的用词选择）。

---

## 14. 主题设定技巧

Topic 设定若过于宽泛可能导致跑题，应具体明确。例如“X improvement of method Y to do Z”可能只涵盖 X+Y/X+Z/Y+Z 的部分内容，若需全面讨论，建议将 X, Y, Z 分开设定为不同 topic。

---

## 15. 专业术语与关键词陷阱

LLM 可能会抓错或漏掉关键概念，例如将 Hamiltonian replica exchange 混淆为 temperature replica exchange（仅抓取 replica exchange）。在 MD 语境下应关注 binding free energy，而在 QM 语境下则应关注 energy，需根据领域特点调整 prompt 或核对结果。

---

## 16. 特殊字符处理错误

文件路径或输入中若包含 Non-ASCII 字符（如希腊字母 Tau），在调用 LLM 时可能导致报错。建议在输入和文件命名阶段仅使用 ASCII 字符以避免此类中断。

---

## 17. 模拟专家角色的配置

当“专家”角色的分工指令未明确时，系统可能仅默认启用一位 basic fact writer，导致输出深度不足。建议配置多位不同背景的“专家”（如一位 computational chemist 和一位 biochemist），以获得更深入的专业讨论（如关于 docking 和 binding free energy 的数据高维度分析）。

---

## 18. 模型与引擎的选择影响

结果的准确性高度依赖于 Search engine 和 LLM 的质量，Google 作为搜索引擎通常优于其他选项。在 LLM 选择上，推荐使用 GPT-4o 或 4o-mini 以获得更好的效果，使用低级模型可能会显著增加生成结果出现幻觉的概率。

---

## 19. 计算资源消耗统计

在测试案例中（约30个主话题，4-5个分支，每个分支包含不同形式和长度的 topics），中间步骤会消耗大量资源。搜索方面消耗了 Tavily free plan 近400次（接近每月1000次的限制），LLM token 消耗主要取决于用户使用的模型（如学校提供的 gpt-4o 或 gpt-4o-mini）。
