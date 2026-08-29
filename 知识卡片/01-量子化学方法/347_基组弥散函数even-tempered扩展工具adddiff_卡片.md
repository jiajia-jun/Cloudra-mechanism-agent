---
id: 347
title: 给基组以even-tempered方式增加弥散函数的工具adddiffuse
domain: 量子化学方法
topic: 基组弥散函数even-tempered扩展工具adddiff
cards: 7
---

## 1. Even-tempered方式构建弥散函数的指数计算公式
Even-tempered构建基组的方式指相邻高斯型函数（GTF）的指数成比例；若当前基组中某个角动量函数中指数最小的是ζ(n)，第二小的是ζ(n-1)，则这个角动量的弥散函数的指数应当为ζ(n)*[ζ(n)/ζ(n-1)]。

---

## 2. 弥散函数指数增加的具体算例
以aug-cc-pVTZ对碳的三层D极化函数指数1.0970000、0.3180000、0.1000000为例，指数最小的两个比例是0.1/0.318=0.314；增加一层弥散函数（构成d-aug-cc-pVTZ）的指数应为0.1*0.314=0.0314，再增加一层（构成t-aug-cc-pVTZ）指数为0.1*0.314^2=0.00986。

---

## 4. adddiffuse工具的输入文件格式要求
adddiffuse启动后需要输入含有Gaussian格式的基组定义的文件，文件可从EMSL上拷贝并包含多个元素，每个元素末尾必须带有****；压缩包内的aug-cc-pVTZ.txt是一个符合要求的输入文件示例。

---

## 5. adddiffuse工具的操作步骤
启动adddiffuse程序后，输入基组定义文件名，然后选择要增加几层弥散函数，接着指定对什么角动量增加弥散函数（如输入SPD表示只增加S、P、D弥散，输入A则对所有角动量增加）；程序会在当前目录下生成添加弥散函数后的Gaussian格式基组定义文件new.txt。

---

## 6. adddiffuse工具对输出文件的格式修改
adddiffuse生成的new.txt文件中，每个元素前面会被加上一个负号；这样在使用gen关键字定义自定义基组时，若将基组定义放在坐标后头，即使其中有的元素没有在当前计算中出现，Gaussian也不会报错。

---

## 7. adddiffuse工具的使用限制
adddiffuse不支持SP壳层，并且如果某个角动量只含有一层基函数，该工具也不会对其增加弥散函数。

---

## 8. adddiffuse工具与EMSL及Gaussian内置定义的区别
基于EMSL上的aug-系列Dunning相关一致性基组，adddiffuse可产生EMSL未完全定义的d-aug-和完全不定义的t-aug-版本；Gaussian内置的d-aug-定义最外层弥散函数指数与EMSL不符，EMSL通过even-tempered方式构建，而Gaussian的来源不明且合理性较差。
