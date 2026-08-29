---
id: 70
title: 安装和使用molproView
url: http://sobereva.com/70
domain: 其他量化软件
topic: molproView安装配置与结果可视化
cards: 7
---
## 1. molproView的功能与替代方案

molproView可以将Molpro计算生成的.xml结果文件转化为网页文件以便在浏览器中查看；若仅用于查看结构或轨道，导出.molden文件使用Multiwfn更为省事。
- 参考文献：http://原作者.com/379，http://原作者.com/269
- 下载地址：http://www.molpro.net/molproView

## 2. molproView基于web服务器的模式

基于web服务器的模式需要主机支持PHP，通过浏览器访问molproView.php并输入.xml文件路径查看结果；配置本机molproView.php可直接载入本地文件，而使用官方服务器需先上传文件。
- 官方服务器地址：http://www.molpro.net/molproView/molproView.php

---

## 3. molproView纯单机模式的安装准备

纯单机模式将molproView作为命令行转换器使用，无需PHP环境；需将molproView压缩包解压到指定目录（如/sob），并下载jmol-11.4.4-binary.tar.gz包至同一目录。
- Jmol下载地址：http://downloads.sourceforge.net/jmol/jmol-11.4.4-binary.tar.gz

---

## 4. 修改Makefile变量与执行编译

在/sob/molproView/Makefile中将JMOLURL变量设为file:/sob以使用本地Jmol包；运行make命令后，Jmol会被解压到/sob/molproView/jmol下，并自动转换example.xml生成example.html。
- 注意事项：默认下载路径不正确，必须手动修改JMOLURL

---

## 5. 生成新结果网页的操作步骤

将新的.xml文件放入/sob/molproView目录下执行make命令，即可快速得到转换后的网页文件；查看图表需联网调用Google在线作图程序。

---

## 6. 安装Linux版Java运行环境

网页浏览器显示分子结构和等值面需要Java支持，需下载Linux RPM版Java运行环境包并安装；需为Firefox添加插件，在/usr/lib/firefox-1.5.0.7/plugins目录执行命令建立软链接。
- 下载地址：http://java.com/en/download/linux_manual.jsp?locale=en&host=java.com
- 命令行：ln -s /usr/java/jre1.6.0_21/plugin/i386/ns7/libjavaplugin_oji.so

---

## 7. 解决access denied权限问题

若显示格点文件处提示access denied，需在/usr/java/jre1.6.0_21/lib/security/java.policy文件中添加指定代码段，授予/sob/molproView/jmol/目录下Java程序访问本地文件的权限。
- 添加内容：
grant codeBase "file:/sob/molproView/jmol/*" {
permission java.security.AllPermission;
};
