---
id: 530
title: 一键把所有gjf文件转成xyz文件、把所有Gaussian输出文件转成gjf文件的脚本
url: http://sobereva.com/530
domain: 化学信息学与脚本
topic: 利用Multiwfn批量转换Gaussian文件格式
cards: 9
---
## 1. 脚本功能与依赖环境

此处提供两个Linux下的Bash shell脚本，利用Multiwfn程序将gjf文件转为xyz文件、或将Gaussian输出文件转为gjf文件。使用前必须恰当安装Multiwfn程序并能通过Multiwfn命令直接启动，建议使用最新版本。脚本可以在Multiwfn的examples\scripts目录下找到，且可改写以支持Multiwfn支持的其他格式转换。相关安装、格式支持及批量运行方法的细节分别参考Multiwfn手册2.1.2节、资料《详谈Multiwfn支持的输入文件类型、产生方法以及相互转换》及《详谈Multiwfn的命令行方式运行和批量运行的方法》。

---

## 2. gjf转xyz脚本使用说明

脚本gjf2xyz.sh可将当前目录下所有Gaussian输入文件（gjf，需为笛卡尔坐标）转换为xyz文件。直接运行脚本即可，转换过程中会显示当前处理的文件名及进度（例如：Converting AlCl3.gjf to AlCl3.xyz ... (2 of 151)）。

---

## 3. out转gjf脚本的配置要求

脚本out2gjf.sh将当前目录下所有Gaussian输出文件（out）转换为gjf文件，运行前必须将Multiwfn的settings.ini文件里的iloadGaugeom设为1。设置iloadGaugeom=1时，若输出文件有输入朝向坐标则生成的gjf使用输入朝向，否则使用标准朝向；若设为2则总是载入标准朝向下的坐标。

---

## 4. out转gjf脚本输出内容说明

脚本生成的gjf文件包含默认关键词，需根据实际情况修改；电荷和自旋多重度与out文件一致（使用赝势的情况除外，需手动修改）。坐标取自输出文件里最后一次输出的数据。关于对称性与朝向问题可参考《谈谈Gaussian中的对称性与nosymm关键词的使用》。

---

## 5. 内坐标输出与扩展后缀支持

若需要输出内坐标的gjf文件，应使用脚本out2gjf_zmat.sh，但乙炔等无法用内坐标描述的体系将无法成功生成。若Gaussian输出文件为log后缀，需将脚本里的out替换为log；也可批量将xyz、mol、mol2、pdb、gro、wfn、wfx、cub等Multiwfn支持的文件转为gjf。

---

## 6. 波函数文件转gjf的特殊操作

将fch、molden、mwfn等含有基函数信息的波函数文件转成gjf文件时，应在脚本的${inf//out/gjf}下面插入一行内容n。这代表不把当前波函数作为初猜信息写入gjf。

---

## 7. gjf文件关键词默认值与批量修改

Multiwfn产生的gjf文件默认关键词为B3LYP/6-31G*。可按照《使用Gaussian时的几个实用脚本和命令》第5节所述方法批量替换所有gjf文件里的关键词。若当前目录下存在template.gjf文件且其中坐标部分用[geometry]或[GEOMETRY]代替，该文件会自动作为模板生成新gjf。

---

## 8. template.gjf模板的高级功能

在使用template.gjf作为模板时，含有[geometry]或[GEOMETRY]的行会被替换为当前体系坐标。若文件中含有[name]字样，这六个字符会被替换为新产生的输入文件名（不含后缀）。若载入的是Gaussian输入/输出文件、ORCA输入文件或含波函数信息的文件，新gjf文件的净电荷和自旋多重度将使用读入的数值，否则沿用template.gjf里的设置。

---

## 9. template.gjf示例内容

template.gjf示例指定B3LYP-D3(BJ)方法，Ag使用SDD赝势基组，C H O使用6-311G*基组，任务为优化和振动分析并生成wfn和chk文件。文件中的%chk=D:\[name].chk、D:\[name].wfn及[geometry]等占位符会在生成具体文件时被替换。
