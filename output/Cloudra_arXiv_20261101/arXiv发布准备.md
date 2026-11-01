# Cloudra arXiv 发布准备

核查日期：2026-11-01。独立审阅见 Astra_审阅.md。该审阅未发现需先补实验或重做评分的科学阻断项。本文件记录发布执行准备；主分类、许可及全体作者公开同意已由作者确认，尚未最终提交文章。

本地当前包已同步 STACKED 架构图及最新正式主文。英文22页、中文18页、SI30页；提交源包63文件，主文图4在第4页。当前可用桌面包为 `~/Desktop/Cloudra_arXiv_提交准备包_20261101.zip`，备份及逐文件校验见本轮本地同步记录。本次不访问或修改远端。

## 已完成

- 正文、SI和完整数据包已在本地，三处小修已同步中英文正文与SI，在Overleaf编译并导出。
- 摘要已另存可直接粘贴的ASCII单段文本，1714字符、220词，低于arXiv官方1920字符上限；无需再缩写。
- 作者顺序为Chengyi Yang、Qianxin Zhou、Yang Li；PDF按该顺序署名，不加共同作者标记。arXiv作者字段只列姓名，身份角色不混入作者名称。
- 实验模型与调用别名、P1b/P2、正式分数与条件性敏感性分开记录；本轮不改科学数据。
- 元信息草案已存arxiv_metadata.json；未发表的文章不填journal-ref或期刊publication DOI。

元信息格式与摘要上限依据[arXiv元信息说明](https://info.arxiv.org/help/prep.html)。

## 发布前落实

| 事项 | 当前状态和最小动作 |
| --- | --- |
| 数据包获取入口 | 已完成：[公开研究数据目录](https://drive.google.com/drive/folders/1yZo3eJuCUuAgedQztgCtLyJcc8MZipf7)提供14.9GB P2完整包、48次P1b实验、Gold证据、完整行为/激活档案和16.8MB SI配套包。公开只读权限和P2云端大小已核实；正文、SI S7、项目README及交付文档已加入链接。 |
| 编译环境 | arXiv现支持XeLaTeX；默认TeX Live2025，另可选2023。当前Overleaf用2026，应在正式上传前用2025试编译并检查实际生成PDF。字体已用.otf文件名加载，符合官方字体查找方式。 |
| 源包精简 | 保留英文主稿所需.tex、.bib和24张实际引用的矢量图。bench_tasks.pdf与bench_tasks_hi.pdf在当前主稿未用，不纳入上传包；不放历史稿、审稿回复、中文稿或中间文件。 |
| SI与数据布局 | 现有桌面准备包已采用两套源文件分别置于manuscript/与supplement/，根目录main.tex和supplement.tex独立编译；数据ZIP位于外层补充数据目录，不混入arXiv源码ZIP。此布局已本地复编，尚未实际上传。 |
| 参考文献 | 当前.bib齐全。arXiv已支持BibTeX自动处理，缺.bbl并非当前阻断项；也可以附与主文件同名且由同一环境生成的.bbl。 |
| 版本标识 | 正文首页仍为Working Draft，SI为Draft。正式发布时清理为统一预印本版本/日期属于成稿整理；本轮三处小修不擅自改变它。 |
| 作者与联系信息 | 当前稿已明确杨程驿（Chengyi Yang）为第一及通讯作者，学校邮箱为202509240114@csust.edu.cn；Qianxin Zhou列第二、Yang Li列第三，不加共同作者标记。ORCID未提供。作者已确认全体作者同意公开；实际作者账号为yyywaa（Chengyi Yang），账户通讯邮箱已验证为202509240114@csust.edu.cn。 |
| 分类 | 作者已确认主分类为cs.MA（Multiagent Systems，多智能体系统）；未选择交叉分类。沿用提交草稿8312079，账户资格以arXiv实际检查为准。 |
| 账号与endorsement | 使用实际作者账号yyywaa（Chengyi Yang），学校邮箱202509240114@csust.edu.cn已验证。邮箱变更后需重新登录；新主分类cs.MA的背书资格待在线检查。 |
| 论文许可 | 作者已明确选择arXiv永久非独占许可，并授权接受提交协议；已在网站接受该协议。论文许可与软件AGPL是不同事项。 |

编译和参考文献依据[TeX Live环境](https://info.arxiv.org/help/faq/texlive.html)、[源文件提交规则](https://info.arxiv.org/help/submit_tex.html)。附件布局依据[ancillary files说明](https://info.arxiv.org/help/ancillary_files.html)。分类依据[官方类别定义](https://arxiv.org/category_taxonomy)。作者字段与发布同意见元信息说明；账号流程见[endorsement](https://info.arxiv.org/help/endorsement.html)；许可选择见[官方许可说明](https://info.arxiv.org/help/license/index.html)。

## 执行顺序

1. 三处小修与Overleaf最终导出已完成；后续冻结主稿、SI、数据包为同一发布版本。
2. 数据公开与正文/SI链接已完成；正式发布时清理Draft字样。
3. 准备精简英文源包，在TeX Live2025下编译并查看生成PDF。
4. 全体作者公开同意和arXiv永久非独占许可已由作者确认，账户邮箱已验证；重新登录后检查cs.MA背书资格。
5. 在arXiv填写元信息、上传并预览；本轮没有上传或提交arXiv。
