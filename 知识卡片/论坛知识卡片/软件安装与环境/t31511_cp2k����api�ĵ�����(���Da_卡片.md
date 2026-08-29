---
key: t31511
title: cp2k����api�ĵ�����(���Dash��Zealʹ��)
url: http://bbs.keinsci.com/thread-31511-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2022
cards: 10
---

# cp2k����api�ĵ�����(���Dash��Zealʹ��) — 知识卡片

## 1. 查阅文档的工具选择

Dash 软件仅支持在 macOS 系统上使用，Windows 和 Linux 系统用户可使用名为 Zeal 的开源软件进行替代。Zeal 是 Dash 的移植版本，其安装过程简单且使用方式与 Dash 类似。Zeal 支持多种官方 API 文档，同时也允许用户导入自定义生成的文档集。

---

## 2. CP2K 文档集的获取方式

社区提供了已经制作好的 CP2K 文档集文件，用户可以直接下载并导入到 Zeal 的 docset 文件夹中使用。该资源的下载链接为 https://pan.baidu.com/s/1EYiVDrFrGxEHovN_-k5DLg，提取码为 afwm。直接使用现成的文件可省去手动编译和配置的步骤。

---

## 3. 获取 CP2K 官方网页手册

用户可以使用 wget 命令镜像下载 CP2K 官方在线手册以构建本地文档，具体的命令为 `wget -m https://manual.cp2k.org/cp2k-2022_1-branch/index.html`。在特定指令下，也可以仅下载 HTML 文件而不包含完整路径结构。此步骤的示例环境为 CentOS 8 系统。

---

## 4. 本地生成 CP2K 输入参考 XML

若需本地生成文档，首先需要编译 CP2K 得到 cp2k.psmp 可执行文件，并运行命令 `cp2k.psmp --xml` 生成 cp2k_input.xml 文件。随后需安装 java 和 saxon 工具，修改环境变量 `export SAXON=/usr/share/java/saxon.jar`，最后执行 `./xml2html` 脚本将 XML 转换为 HTML 文档。

---

## 5. 文档集目录结构创建

构建 docset 需要在本地建立特定的目录结构，包括创建主目录和子目录。具体命令为 `mkdir -p cp2k.docset` 和 `mkdir -p cp2k.docset/Contents/Resources/Documents`。建立好目录后，需将下载或生成的 HTML 手册文件移动到 `cp2k.docset/Contents/Resources/Documents/` 路径下。

---

## 6. 文档集 Info.plist 配置文件

文档集需要在 `cp2k.docset/Contents/` 路径下创建名为 Info.plist 的配置文件，以定义文档集的基本属性。该文件包含 CFBundleIdentifier、CFBundleName、DocSetPlatformFamily 等键值对，其中 `isDashDocset` 键需设置为 `true`。配置内容需遵循 Apple Property List 格式规范。

---

## 7. 文档集索引数据库初始化

使用 SQLite3 工具在 `cp2k.docset/Contents/Resources/` 目录下创建名为 docSet.dsidx 的数据库文件。需执行 SQL 命令 `CREATE TABLE searchIndex(id INTEGER PRIMARY KEY, name TEXT, type TEXT, path TEXT)` 来建立搜索索引表。初始化完成后即可退出数据库交互界面。

---

## 8. 文档集索引数据的 Python 生成脚本

需要编写并运行 Python 脚本 docset.py 来解析 HTML 文件并向数据库写入索引数据。脚本利用 BeautifulSoup 库读取 `index.html`，提取所有超链接标签的文本和 href 属性，并将非首页链接作为 'func' 类型存入 searchIndex 表中。脚本执行前需确保安装了 bs4 和 sqlite3 库。

---

## 9. 文档集图标文件设置

文档集的图标文件源自原网页的 favicon.png，需将其复制并重命名以符合 Zeal 的显示要求。执行命令 `cp cp2k.docset/Contents/Resources/Documents/favicon.png cp2k.docset/icon@2x.png` 可设置高清图标。此外，还需将 favicon.png 修改尺寸为 16x16 并重命名为 icon.png 以作为普通图标。

---

## 10. 文档集的最终安装

将制作完成的 cp2k.docset 文件夹移动或复制到 Zeal 软件指定目录下的 docset 文件夹中，即可完成文档的安装与加载。用户随后可在 Zeal 软件中搜索和查阅 CP2K 的相关文档内容。
