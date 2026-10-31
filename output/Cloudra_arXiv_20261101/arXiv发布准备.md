# Cloudra arXiv 发布准备

核查日期：2026-11-01。独立审阅见 Astra_审阅.md。该审阅未发现需先补实验或重做评分的科学阻断项。本文件记录发布执行准备，不替作者选择许可或提交文章。

## 已完成

- 正文、SI和完整数据包已在本地，三处小修已同步中英文正文与SI，在Overleaf编译并导出。
- 摘要已另存可直接粘贴的ASCII单段文本，1774字符、222词，低于arXiv官方1920字符上限；无需再缩写。
- 作者顺序为Chengyi Yang、Qianxin Zhou、Yang Li；PDF保留共同第二作者说明。arXiv作者字段只列姓名，身份角色不混入作者名称。
- 实验模型与调用别名、P1b/P2、正式分数与条件性敏感性分开记录；本轮不改科学数据。
- 元信息草案已存arxiv_metadata.json；未发表的文章不填journal-ref或期刊publication DOI。

元信息格式与摘要上限依据[arXiv元信息说明](https://info.arxiv.org/help/prep.html)。

## 发布前落实

| 事项 | 当前状态和最小动作 |
| --- | --- |
| 数据包获取入口 | Cloudra_SI_Data.zip约16.8MB，材料已齐；需要随文章附上或放到公开可下载位置，并在SI S7写清入口及对应版本。当前GitHub仓库是private，不能作为普通读者已经可访问的获取方式。代码可以继续如实写未来开源计划。 |
| 编译环境 | arXiv现支持XeLaTeX；默认TeX Live2025，另可选2023。当前Overleaf用2026，应在正式上传前用2025试编译并检查实际生成PDF。字体已用.otf文件名加载，符合官方字体查找方式。 |
| 源包精简 | 保留英文主稿所需.tex、.bib和24张实际引用的矢量图。bench_tasks.pdf与bench_tasks_hi.pdf在当前主稿未用，不纳入上传包；不放历史稿、审稿回复、中文稿或中间文件。 |
| SI与数据布局 | 可将SI PDF和数据ZIP放提交包根目录的anc/。如希望主PDF自动连同SI编译，应把两套源文件按互不冲突的路径整理，再检查根目录相对路径。anc中不放TeX源文件。此布局尚未选择，也未实际上传。 |
| 参考文献 | 当前.bib齐全。arXiv已支持BibTeX自动处理，缺.bbl并非当前阻断项；也可以附与主文件同名且由同一环境生成的.bbl。 |
| 版本标识 | 正文首页仍为Working Draft，SI为Draft。正式发布时清理为统一预印本版本/日期属于成稿整理；本轮三处小修不擅自改变它。 |
| 作者与联系信息 | 由各作者确认最终稿、姓名、单位、贡献及发布同意。确定提交账户、联系邮箱；通讯作者和ORCID尚未从当前署名中取得，不补造。 |
| 分类 | 建议physics.chem-ph为主类，cs.AI可选交叉分类；这是按化学机理与规划/验证内容作出的建议，尚未提交选择。 |
| 账号与endorsement | 使用实际作者账号。首次投稿或首次进入新类别可能需要endorsement，取决于账户；机构邮箱有助于流程。 |
| 论文许可 | 由作者结合拟投期刊/基金要求选择，例如CC BY4.0或arXiv非独占分发许可；本轮未代选或接受。论文许可与软件AGPL是不同事项。 |

编译和参考文献依据[TeX Live环境](https://info.arxiv.org/help/faq/texlive.html)、[源文件提交规则](https://info.arxiv.org/help/submit_tex.html)。附件布局依据[ancillary files说明](https://info.arxiv.org/help/ancillary_files.html)。分类依据[官方类别定义](https://arxiv.org/category_taxonomy)。作者字段与发布同意见元信息说明；账号流程见[endorsement](https://info.arxiv.org/help/endorsement.html)；许可选择见[官方许可说明](https://info.arxiv.org/help/license/index.html)。

## 执行顺序

1. 三处小修与Overleaf最终导出已完成；后续冻结主稿、SI、数据包为同一发布版本。
2. 定下SI/数据公开方式，补真实获取入口，清理Draft字样。
3. 准备精简英文源包，在TeX Live2025下编译并查看生成PDF。
4. 作者确认发布及许可，核对账号是否需要endorsement。
5. 在arXiv填写元信息、上传并预览；本轮没有上传或提交arXiv。
