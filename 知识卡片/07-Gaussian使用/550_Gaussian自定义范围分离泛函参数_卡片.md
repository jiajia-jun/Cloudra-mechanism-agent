---
id: 550
title: 在Gaussian中自定义范围分离泛函的方法
domain: Gaussian使用
topic: Gaussian自定义范围分离泛函参数
cards: 11
---

## 1. Gaussian自定义泛函时IOp的作用域限制
Gaussian做多步任务时IOp设置仅对第一个任务生效，因此使用自定义泛函进行opt和freq任务时必须分别执行。如果在一个任务中连续写opt freq，freq任务接收不到IOp会导致使用非预期泛函，从而造成严重问题。

---

## 2. LC形式与CAM形式的1/r12算符划分差异
LC形式将长程部分完全用HF交换项描述而短程部分完全用GGA交换泛函描述，而CAM形式额外引入了α和β参数。CAM形式下长程极限的HF成份是α+β，短程极限的HF成份是α，这使得CAM-B3LYP等泛函在保持精度的同时比LC泛函在热化学数据上表现更好。

---

## 3. 定义范围分离泛函交换能的Gaussian IOp参数
Gaussian中定义范围分离泛函交换部分的关键IOp包括：IOp(3/107)和(3/108)定义HFx和DFx的wLong和wShort，IOp(3/119)和(3/120)定义cLong和cShort，IOp(3/130)和(3/131)定义cFull。w参数设定为MMMMMNNNNN代表wLong=MMMMM/10000、wShort=NNNNN/10000，一般3/107和3/108定义的值总是相等的。

---

## 4. Gaussian中范围分离泛函的系数计算规则
Gaussian通过cFull、cLong、cShort定义系数，其中cFull+cLong对应长程系数，cFull+cShort对应短程系数，cFull相当于中程系数。对于wShort为0的情况，HFx的实际系数是ScaHFX*HFx_cShort (短程) 或 ScaHFX*HFx_cLong (长程)，而DFx的实际系数是1 - DFx_cShort (短程) 或 1 - DFx_cLong (长程)。

---

## 5. IOp(3/130)与IOp(3/131)的符号控制
IOp(3/130=NNNNN)设置HFx cFull为NNNNN/10000时，如果令十万、百万、千万位设1，说明分别将HFx cShort、HFx cLong、HFx cMedium取负。设置DFx的IOp(3/131)的用法也是如此。

---

## 6. LC-PBE泛函的参数特征与输出解读
LC-PBE泛函的短程HF成份为0%，长程为100%，w=0.47。在Gaussian输出中表现为HFx和DFx的wShort=0、wLong=0.47，且cShort=0、cLong=1。对于wShort=0的情况，HFx与DFx精确互补，即某个范围内DFx设的系数若为c，则真正用的系数为1-c。

---

## 7. CAM-B3LYP泛函的参数特征与输出解读
CAM-B3LYP泛函的短程HF成份为19%，长程为65%，w=0.33。在Gaussian输出中，cFull=0.19 (对应α)，cLong=0.46 (对应β)，且LYP梯度校正部分的系数是0.81。此泛函的DFT交换项和HF交换项也是精确互补的。

---

## 8. wB97X泛函的参数特征与输出解读
wB97X泛函的w=0.3，短程HF成份为15.77%，长程为100%。在Gaussian输出中，HFx的cFull=0.157706、cLong=0.842294，而DFx的cFull=0、cLong=1。这表明wB97X在短程部分DFT交换项实际系数为1，在长程部分DFT交换项实际系数为0，二者不精确互补。

---

## 9. 在Gaussian中从头定义CAM-B3LYP的IOp设置
在Gaussian中使用IOp从头定义原始的CAM-B3LYP泛函需要使用BV5LYP关键词配合一系列IOp。设置如下：IOp(3/76=1000010000,3/77=1000010000,3/78=0810010000) 定义基础交换相关系数，IOp(3/107=0330000000,3/108=0330000000) 定义w=0.33，IOp(3/119=0460000000,3/120=0460000000) 定义β，IOp(3/130=01900,3/131=01900) 定义α。

---

## 10. 修改CAM-B3LYP的α、β和w参数的方法
若要修改CAM-B3LYP的α、β和w参数，只需修改Overlay 3里面的IOp(3/107)、(3/108)、(3/119)、(3/120)、(3/130)、(3/131)，而保持3/76、3/77、3/78与原CAM-B3LYP一致。例如设定α=0.15、β=0.4、w=0.25，则使用：IOp(3/107=0250000000,3/108=0250000000) IOp(3/119=0400000000,3/120=0400000000) IOp(3/130=01500,3/131=01500)。

---

## 11. 在Gaussian中定义LC-PBE0泛函的方法
LC-PBE0泛函参数为w=0.3、α=0.25、α+β=1.0，可在Gaussian中通过PBEPBE关键词配合IOp定义。设置如下：IOp(3/76=1000010000,3/77=1000010000) 将PBE设为100% HF交换+100% DFT交换，IOp(3/107=0300000000,3/108=0300000000) 设w=0.3，IOp(3/119=0750000000,3/120=0750000000) 设cLong=0.75，IOp(3/130=02500,3/131=02500) 设cFull=0.25。
