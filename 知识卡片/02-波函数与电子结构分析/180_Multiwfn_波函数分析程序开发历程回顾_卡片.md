---
id: 180
title: 杂谈Multiwfn从1.0到3.0版的开发经历
url: http://sobereva.com/180
domain: 波函数与电子结构分析
topic: Multiwfn_波函数分析程序开发历程回顾
cards: 1
---

# Multiwfn_波函数分析程序开发历程回顾 — 知识卡片

## 1. Multiwfn 1.0版发布时间与来源

Multiwfn 1.0版本于2009年11月27日正式发布到论坛上；2010年3月在codeplex上建立了项目主页，即Multiwfn官网。

## Multiwfn官网地址变更
由于微软codeplex开源项目已停止运营，Multiwfn主页已变更为http://sobereva.com/multiwfn。

## Multiwfn全称与来源
Multiwfn的全称是Multifunctional wavefunction analyzer，名字主要来源于wavefunction analysis（波函数分析）这一概念；该叫法作者最初从《Introduction to Computational Chemistry (2ed, Jensen)》第9章标题中学来，后在Cioslowski于《Encyclopedia of Computational Chemistry》中的章节标题中也看到了同样的用法。

## Multiwfn早期版本发布时间表
Multiwfn 1.x系列各版本发布时间如下：1.0版于2009年11月27日发布，1.1版于2010年1月17日发布，1.2版于2010年2月9日发布，1.3版于2010年4月24日发布，1.4版于2010年7月8日发布，1.5版于2010年10月2日发布。

## Multiwfn 1.5手册规模
Multiwfn 1.5版的手册为纯中文，内容相对简单，主要包含大量例子，系统性和理论介绍较少；该版本手册字数达到了两万七千字。

## Multiwfn首次被学术刊物引用
Multiwfn于2010年底首次被正经学术刊物的文章引用，文献出处为J. Phys. Chem. A, 114, 13257。

## Multiwfn 2.0版发布时间
Multiwfn 2.0版本于2011年3月9日发布，标志着Multiwfn正式进入学术同行的视野。

## Multiwfn 2.0手册规模与特点
Multiwfn 2.0手册为详细的英文版，约90页；手册不仅讲解程序操作，还特意详细介绍了所有涉及的理论，实例旨在展现一定的物理意义，编写时间约为开发程序时间的1/3。

## Multiwfn编译环境迁移
Multiwfn 2.0版之前在Compaq Visual Fortran 6.5环境下开发；从2.0版开始改用Intel Visual Fortran以支持OpenMP并行化；Windows版源代码包中至今仍保留CVF6.5的编译方法。

## Multiwfn程序介绍文章
Multiwfn程序的介绍文章发表于J. Comp. Chem. 33, 580-592 (2012)，对应Multiwfn 2.1.2版；作者希望用户引用该文。

## AIM理论创始人Bader逝世
AIM理论的创始人Bader于2012年1月15日因肺病逝世。

## Multiwfn 2.x系列核心功能开发计划
Multiwfn 2.x系列版本的开发计划包括加入ELF/LOL/拉普拉斯函数的拓扑分析、AdNDP、CDA、定量分子表面分析、盆分析等功能。

## Multiwfn 2.1版发布时间与功能
Multiwfn 2.1版于2011年6月26日发布，加入了电子密度的拓扑分析功能。

## Multiwfn 2.2版发布时间与功能
Multiwfn 2.2版于2011年11月28日发布，加入了ELF/LOL/拉普拉斯函数的拓扑分析功能；开发过程中推导并调试了ELF/LOL的导数公式及电子密度的三阶导数。

## Multiwfn 2.3版发布时间与功能
Multiwfn 2.3版于2012年2月18日发布，加入了定量分子表面分析功能，并将GsGrid程序的全部功能整合进主功能13，此后GsGrid不再更新。

## Multiwfn 2.4版发布时间与功能
Multiwfn 2.4版于2012年5月6日发布，加入了AdNDP功能。

## Multiwfn 2.5版发布时间与功能
Multiwfn 2.5版于2012年8月1日发布，加入了模糊空间分析功能，用于提出基于模糊重叠空间的定义键级的方法。

## Multiwfn 2.6版发布时间与功能
Multiwfn 2.6版于2012年11月6日发布，加入了CDA功能。

## Multiwfn 3.0版发布时间与规模
Multiwfn 3.0版本于2013年发布；代码量约为三万行，是最初版本的50倍；手册页数为257页，是2.0版本的近三倍。

## Multiwfn 3.0版核心功能更新
Multiwfn 3.0版加入了盆分析功能，该功能于2013年春节期间集中开发完成，解决了此前认为算法复杂、深不可测的难题。

## Multiwfn未来发展方向
Multiwfn的未来发展计划包括支持基于平面波的程序、支持ADF、支持Crystal09程序、改进等值面显示速度和效果、支持分布多极分析(DMA)、加快静电势计算速度、支持AOSB键级分解、支持电荷转移积分等。

## Multiwfn等值面显示问题
Multiwfn在显示等值面图时（除mesh方式外）存在颜色对比度低或有块状黑影的问题，显示速度不理想，Linux版中常出现黑块；这依赖于DISLIN图形库的局限性。

## Multiwfn程序设计原则
Multiwfn的程序设计坚持以下三点原则：(1)令计算速度最大化，计算量大的代码使用OpenMP并行化；(2)使界面设计尽可能容易理解，提示信息包含输入例子，操作流程简洁；(3)力图使结果能直接可视化，同时支持导出数据供第三方程序作图。

## Multiwfn计算速度优化实例
作者曾花费约五天时间反复琢磨静电势平面计算的代码，最终使计算时间比最初版本降低了一个数量级；一度因过度优化忽略指数函数导致离分子稍远区域的静电势计算出错，后改为更稳健的优化方式。
