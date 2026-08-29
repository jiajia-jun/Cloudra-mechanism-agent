---
id: 602
title: 巨幅降低Multiwfn结合VMD绘制分子表面静电势图耗时的一个关键技巧
domain: 可视化与制图
topic: Multiwfn结合VMD绘制静电势图加速技巧
cards: 10
---

## 1. 减少Multiwfn计算静电势格点数据耗时的原理
VMD将静电势映射到电子密度等值面时仅利用等值面附近格点的静电势插值，忽略距离范德华表面较远的格点可以巨幅节约计算耗时。这个想法已实现进Multiwfn，耗时降低了一个数量级，且比调用Gaussian自带的cubegen程序速度更快。读者必须使用2021-Jun-30及以后更新的Multiwfn版本。

---

## 2. 静电势计算范围控制参数ESPrhoiso
在Multiwfn的settings.ini里设置参数ESPrhoiso为非0值（如0.001），代表计算静电势格点数据时仅计算电子密度等值面附近的格点，其它格点的静电势直接被当做0。该参数也可以通过命令行设置，例如`Multiwfn nico.wfn -ESPrhoiso 0.001`，命令行参数设置的优先级高于settings.ini。

---

## 3. ESPiso脚本默认开启的加速设置
从2021-Jun-30更新的Multiwfn开始，自带的ESPiso.bat和ESPiso.sh脚本里已经默认加了`-ESPrhoiso 0.001`选项。计算静电势格点数据时Multiwfn窗口会显示检测到的等值面附近格点数量，提示例如：`Number of grids to calculate ESP: 56473`。

---

## 4. ESPrhoiso参数值必须与VMD绘图等值面值匹配
使用ESPiso.vmd脚本在VMD中绘图时，ESPrhoiso的设定值必须与想要绘制的电子密度等值面值保持一致。如果ESPrhoiso设为0.001，而在VMD里把电子密度等值面手动改为0.002，等值面颜色就会显示异常。

---

## 5. 加速方法与cubegen调用的互斥性
使用这种节约耗时的做法时不能让Multiwfn调用cubegen来算静电势格点数据，否则加速效果无效。

---

## 6. 边界格点检测参数ESPrhonlay的机制
settings.ini里的ESPrhonlay参数（简写为n）用于定义检测范围，Multiwfn检测格点周围n层格点里是否存在电子密度有的大于ESPrhoiso而有的小于ESPrhoiso的情况，若是则视为边界格点。n=1检验周围26个格点，n=2检验周围两层共124个格点，n=2时被判断为边界格点的数目比n=1时大约多一倍。

---

## 7. 参数ESPrhonlay的默认值与图像质量
ESPrhonlay默认为1，此时为了弥补VMD插值可能利用到未计算格点（静电势被视为0）导致的颜色瑕疵，Multiwfn会自动将边界格点的静电势赋予给相邻的非边界格点。实测显示这种处理下n=1的图像效果与n=2没有任何区别，而计算成本更便宜，不损害图像视觉效果。

---

## 8. 小分子体系多巴胺的加速测试数据
测试对象为B3LYP/6-311G**计算的多巴胺（22原子），使用Intel i7-10870H CPU和Medium quality grid设置：Multiwfn内部代码耗时179秒；使用`-ESPrhoiso 0.001`仅计算28374个点（占总点数5%）耗时10秒；调用cubegen耗时33秒。加速后耗时降低了约20倍。

---

## 9. 大分子体系瑞德西韦的加速测试数据
测试对象为B3LYP/6-31G*计算的瑞德西韦（77原子），使用双路E5-2696v3 CPU和High quality grid设置：使用`-ESPrhoiso 0.001`耗时69秒；调用cubegen耗时105秒。利用该技巧耗时明显低于调用cubegen。在普通8核CPU上使用默认脚本计算，总耗时仅55秒。

---

## 10. 该加速方法的适用体系范围
对于一般体系，用这种方法比调用cubegen耗时更低且能监控计算进度。但对于非常大的体系（如150~200个原子及以上），调用cubegen大概率会快于此方法。对于超大体系可参考《巨大体系的范德华表面静电势图的快速绘制方法》调用cubegen。
