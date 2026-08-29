---
key: t25833
title: ʹ��MolAICal��OnionNetģ�ͽ���ҩ���׺�����Ԥ��
url: http://bbs.keinsci.com/thread-25833-1-1.html
domain: 其他量化软件
source: keinsci
year: 2021
cards: 13
---

# ʹ��MolAICal��OnionNetģ�ͽ���ҩ���׺�����Ԥ�� — 知识卡片

## 1. MolAICal 简介

MolAICal 集成了深度学习模型与结构搜索算法，支持基于深度学习模型 OnionNet 进行结合亲和力预测。用户可以使用该工具了解深度学习模型及结构搜索与底层深度学习预测流程。该工具也允许用户训练自己的模型以实现特定研究目的。更多详细信息可查阅相关文献。

---

## 2. MolAICal 官方资源

MolAICal 的官方主页地址为 https://molaical.github.io。国内用户可访问 https://molaical.gitee.io。中文教程地址为 https://molaical.github.io/cntutorial.html。

---

## 3. OnionNet 模型安装平台

安装 OnionNet 模型目前仅支持 Linux 系统。安装过程中需要下载压缩包并移动至指定目录。

---

## 4. 下载 OnionNet 模型文件

需访问 DownloadModel 页面下载模型文件。在打开的页面路径 science/AImodels/BindingAffinity/onionnet/linux 下查找文件名为 onionnet.tar.gz 的压缩包。

---

## 5. OnionNet 模型文件放置与解压

将下载的 onionnet.tar.gz 文件移动到 MolAICal-xxx/mtools 目录下。在 MolAICal-xxx 目录（即安装 MolAICal 的目录）下的 mtools 目录中执行解压操作。

---

## 6. 解压与进入目录命令

使用命令 `tar -xzvf onionnet.tar.gz` 解压文件。解压后使用命令 `cd onionnet` 进入 onionnet 目录。

---

## 7. OnionNet 模型安装命令

进入 onionnet 目录后，执行 `chmod +x install.sh` 赋予安装脚本执行权限。随后执行 `./install.sh` 运行安装脚本以完成模型安装。

---

## 8. 单个配体-受体复合物拼合

使用 mergeon 模型可以将配体与受体拼合为一个复合物文件。基础命令格式为 `molaical.exe -model mergeon -r [受体文件] -l [配体文件] -c [复合物输出文件]`。示例中受体文件为 1a30_protein.pdb，配体文件为 1a30_ligand.mol2.pdb，输出复合物文件为 1a30_complex.pdb。

---

## 9. 配体文件格式转换

若用户输入文件格式非 pdb 格式，需先使用 MolAICal 进行格式转换。例如将 mol2 格式转换为 pdb 格式，可使用命令 `molaical.exe -tool format -i ligand.mol2 -o ligand.pdb`。输入文件需带有正确格式的后缀名（如 .mol2, pdb），否则 MolAICal 无法自动识别。

---

## 10. 单个复合物结合亲和力预测

将拼合得到的复合物文件放入同一文件夹。使用 onionnet 模型进行 pKx（pKa or pKi）预测的命令为 `molaical.exe -model onionnet -i inputlist.dat -o results.csv`。计算完成后会生成包含 pKx 值的 results.csv 文件。

---

## 11. 结合亲和力单位转换

若需要将计算得到的 pKx 值转换为结合自由能，可参考 MolAICal 教程页面（https://molaical.github.io/tutorial.html）。MolAICal 提供了相关的单位转换模块。

---

## 12. 批量拼合复合物

研究若需对多个配体进行结合亲和力预测，需先将多个配体与受体拼合形成复合物。可将配体列表写入 list.txt 文件，并指定受体文件（如 GCGRNoLigand.pdb）。批量拼合命令为 `molaical.exe -model mergeon -r GCGRNoLigand.pdb -f list.txt`。拼合完成后会生成名为 complex_<yourligand name>.pdb 的文件。

---

## 13. 批量预测结合亲和力

使用 shell 命令 `ls -A complex_*.pdb > complexList.txt` 将所有合并的复合物文件名写入 complexList.txt。随后使用命令 `molaical.exe -model onionnet -i complexList.txt -o results.csv` 进行批量计算。计算结果将输出包含所有 pKx 值的 csv 文件（results.csv）。
