---
key: t27100
title: ����һ���Ƴ��ɰ�Intel OneAPI�Ľű�
url: http://bbs.keinsci.com/thread-27100-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2021
cards: 6
---

# ����һ���Ƴ��ɰ�Intel OneAPI�Ľű� — 知识卡片

## 1. Intel oneAPI 离线安装包体积

Intel oneAPI 的离线安装包包含完整版本和子组件版本，完整版本单次更新下载量约为 20G。
- 每次更新完整安装包会占用大量磁盘空间。

---

## 2. 旧版本清理与更新策略

官方建议在安装新版本前删除旧版本以节省空间，用户可通过 `--config` 选项自定义保留的版本。
- 卸载旧版本可避免磁盘空间占用过高。

---

## 3. Linux 系统下的批量卸载方案

针对 openSUSE 系统可使用 `zypper` 命令，CentOS 系统可将命令中的 `zypper` 替换为 `dnf` 进行包管理。
- 删除旧版本需要先筛选出已安装的 oneAPI 包。

---

## 4. 旧包筛选命令

使用以下命令行组合获取已安装的 oneAPI 包名：
```bash
command = "zypper search -i oneapi | grep oneapi | awk '{print $3}'"
```
- 该命令通过 `grep` 和 `awk` 提取包名信息。

---

## 5. 正则表达式匹配规则

使用如下正则表达式模式匹配旧的 oneAPI 安装包：
```python
pattern = re.compile(r"^intel\-oneapi\-([a-zA-Z]+\-)+[0-9\.]+$")
```
- 该规则用于过滤包名以确保准确性。

---

## 6. Python 自动化卸载脚本

通过 Python 脚本 `get_old_oneapi.py` 自动识别并生成旧版本包列表，结合包管理器进行批量卸载。
- 执行卸载的命令示例如下：
```bash
zypper remove $(get_old_oneapi.py)
```
