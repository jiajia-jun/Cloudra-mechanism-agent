---
key: b602
title: 巨幅降低Multiwfn结合VMD绘制分子表面静电势图耗时的一个关键技巧
url: http://sobereva.com/602
domain: 可视化与制图
source: blog
year: 2021
cards: 13
---

# 巨幅降低Multiwfn结合VMD绘制分子表面静电势图耗时的一个关键技巧 — 知识卡片

## 1. Multiwfn加速绘制分子表面静电势图的核心原理

VMD在将静电势映射到电子密度等值面时，仅实际利用了等值面附近格点的静电势进行插值。若忽略距离范德华表面较远格点的静电势计算，仅计算特定电子密度等值面附近的格点，可巨幅降低计算耗时。

---

## 2. ESPrhoiso参数的定义与设置方法

`ESPrhoiso`参数用于指定计算静电势的目标电子密度等值面，默认值为0表示不启用加速。若将该参数设为非零值（如0.001），则Multiwfn在计算静电势时仅计算该电子密度等值面附近的格点，其余格点静电势直接视为0。

---

## 3. ESPrhoiso参数的命令行设置方式

`ESPrhoiso`参数既可在`settings.ini`文件中修改，也可通过命令行设置。命令行设置的优先级高于`settings.ini`，例如输入命令`Multiwfn nico.wfn -ESPrhoiso 0.001`即可启用该加速模式。

---

## 4. ESPiso脚本默认加速设置

自2021年6月30日起，Multiwfn自带的`ESPiso.bat`和`ESPiso.sh`脚本默认添加了`-ESPrhoiso 0.001`选项。在计算静电势格点数据时，程序会自动检测并仅计算电子密度为0.001 a.u.等值面附近的格点。

---

## 5. 加速模式下ESPrhoiso与VMD等值面值的匹配

使用此加速方法时，`ESPrhoiso`的设定值必须与VMD中最终绘制的电子密度等值面值保持一致。例如设定`ESPrhoiso`为0.001时，若在VMD中将等值面手动改为0.002，图像颜色会出现异常。

---

## 6. 加速模式与cubegen的互斥性

启用基于`ESPrhoiso`的节约耗时做法时，不能让Multiwfn调用Gaussian自带的`cubegen`程序计算静电势，否则该加速设置无效。

---

## 7. ESPrhonlay参数对计算边界格点的影响

`ESPrhonlay`参数（默认为1）决定了电子密度等值面附近边界格点的判定范围。程序检测当前格点周围`n`层格点内是否存在电子密度大于和小于`ESPrhoiso`的情况，以此判断是否为需要计算静电势的边界格点。

---

## 8. ESPrhonlay参数对耗时与图像质量的影响

`ESPrhonlay`设为1时计算速度比设为2快约一倍。虽然设为1可能导致个别区域因VMD插值利用了未计算格点而产生轻微瑕疵，但Multiwfn会自动对非边界格点进行修正，使得`ESPrhonlay=1`的图像效果与`ESPrhonlay=2`无区别。

---

## 9. 多巴胺体系加速测试数据（Medium quality）

在Intel i7-10870H CPU下，对多巴胺（B3LYP/6-311G**）使用Medium quality grid计算静电势：Multiwfn内部代码耗时179秒；启用`-ESPrhoiso 0.001`后耗时10秒；调用cubegen耗时33秒。

---

## 10. 多巴胺体系加速测试数据（Low quality）

使用`ESPiso.bat`默认的Low quality grid设置对多巴胺进行计算，在`-ESPrhoiso 0.001`设置下仅需4秒即可完成。

---

## 11. 瑞德西韦体系加速测试数据（High quality）

在双路E5-2696v3（36核）CPU下，对瑞德西韦（B3LYP/6-31G*）使用High quality grid计算静电势：Multiwfn启用`-ESPrhoiso 0.001`耗时69秒；调用cubegen耗时105秒。

---

## 12. 瑞德西韦体系在个人电脑上的测试数据

在Intel i7-10870H（8核）个人电脑上，利用`ESPiso.bat`（Medium quality电子密度网格+Low quality静电势网格）结合`-ESPrhoiso 0.001`计算瑞德西韦，总耗时仅为55秒。

---

## 13. 加速方法的适用范围与局限性

该方法对一般体系和未安装Gaussian的用户优势显著，且具备计算进度监控功能。但对于150~200原子以上的超大体系，调用`cubegen`的速度通常快于此方法，此时建议优先调用`cubegen`。
