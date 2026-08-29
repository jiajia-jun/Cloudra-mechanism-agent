---
key: b447
title: 使用Multiwfn+VMD快速绘制高质量分子轨道等值面图（含视频）
url: http://sobereva.com/447
domain: 可视化与制图
source: blog
year: 2018
cards: 21
---

# 使用Multiwfn+VMD快速绘制高质量分子轨道等值面图（含视频） — 知识卡片

## 1. Multiwfn与VMD联用绘制分子轨道的优势

Multiwfn与VMD联用绘制分子轨道等值面图的方法相比常用的GaussView具有完全免费、显示效果更佳、计算耗时极少（尤其对大体系）的优势。
- 该方法适合追求高质量图像和计算效率的场景。

---

## 2. 支持的输入文件类型

Multiwfn支持.fch/.fchk、.molden、.mwfn文件以及GAMESS-US或Firefly程序的输出文件作为输入来绘制轨道。
- 任何能向Multiwfn提供基函数信息的文件均可以使用。

---

## 3. 准备工作：配置脚件

将Multiwfn安装包examples\scripts目录下的showorb.bat和showorb.txt复制到Multiwfn可执行文件所在目录。
- 编辑showorb.bat，将输入文件名修改为实际文件名，并将VMD路径设置为实际安装路径（若含空格需加双引号）。

---

## 4. 设置绘制轨道序号范围

showorb.txt文件中的每一行对应Multiwfn界面中需要输入的命令。
- 编辑该文件第三行以设定要绘制的轨道序号范围，格式支持单列表和范围缩写（如10,20-23,28-30）。

---

## 5. 配置VMD绘图脚本

将examples\scripts目录下的VMD绘图脚本showorb.vmd复制到VMD目录下，并在VMD目录下的vmd.rc文件末尾插入命令source showorb.vmd。
- VMD启动时会自动执行该脚本，定义orb、orbiso、orbclean三个命令。

---

## 6. VMD脚本命令：orb

在VMD文本窗口输入orb [序号]命令，可载入并显示对应序号的轨道等值面图。
- 输入新序号会自动撤销当前轨道显示并切换至新轨道，默认等值面数值为0.05。

---

## 7. VMD脚本命令：orbiso

在VMD文本窗口输入orbiso [数值]命令，可修改当前显示的轨道等值面数值。
- 例如输入orbiso 0.02可将等值面数值修改为0.02。

---

## 8. VMD脚本命令：orbclean

在VMD文本窗口输入orbclean命令，可删除VMD目录下所有orb开头的.cub文件。
- 此操作用于防止文件堆积。

---

## 9. 运行批处理生成Cube文件

双击运行showorb.bat后，脚本会自动调用Multiwfn计算指定轨道的格点数据并导出为cube文件至VMD目录。
- 生成的文件命名规则为orb加上6位数字编号，如orb000020.cub。

---

## 10. 实例：NH2-biphenyl-NO2体系绘制

使用Multiwfn自带的NH2-biphenyl-NO2体系（D-pi-A.fchk）作为输入，设置轨道范围为54-59（HOMO-2至LUMO+2）。
- 运行后在VMD中输入orb 56可查看HOMO轨道，默认正负相位分别以红蓝色显示。

---

## 11. Beta轨道的序号规则

对于非限制性开壳层波函数，Multiwfn中Beta轨道序号排在Alpha轨道之后。
- 若体系有x个基函数，则第1号Beta轨道在Multiwfn中的序号为x+1，设置showorb.txt时需遵循此规则。

---

## 12. 查看Beta轨道序号的方法

若不确定Beta轨道对应的序号，可在Multiwfn主功能0界面输入负值（如-30）查看第30号Beta轨道的实际序号。
- 也可通过界面左上角Orbital info.选项输出所有轨道信息进行查询。

---

## 13. VMD原子序号显示

VMD 1.9.3版本没有自带显示原子序号的功能。
- 可通过外部脚本实现原子序号显示，效果不佳时可借助图像处理软件修饰。

---

## 14. 使用Tachyon渲染器提升画质

使用Tachyon渲染器对图像进行渲染可以获得比VMD图形窗口直接显示更好的材质效果和抗锯齿效果。
- Tachyon的使用方法参考相关教程文档。

---

## 15. 修改轨道显示材质

默认等值面显示材质为Glossy，可通过VMD的Graphics - Representation界面手动修改为EdgyGlass或Translucent等透明材质。
- 也可直接编辑showorb.vmd文件，将Glossy替换为 desired 材质名称。

---

## 16. 修改轨道相位颜色

轨道正负相位的默认颜色分别为红色（正）和蓝色（负）。
- 可在VMD的Graphics - Representation界面修改Color ID值，或编辑showorb.vmd中的ColorID参数。

---

## 17. 调整格点质量

脚本默认使用中等质量格点（总点数约512000个），对于100原子以上的较大体系可能导致等值面有棱角。
- 此时建议将showorb.txt第四行的数值由2改为3以启用高质量格点计算。

---

## 18. 绘制里德堡轨道的设置

绘制里德堡轨道时，默认的延展距离可能不足导致小等值面数值下图形被截断。
- 应在showorb.txt第三行和第四行之间插入-10和12两行，将延展距离加大到12 Bohr。

---

## 19. 增量计算轨道

若已计算过部分轨道（如20-30），后续需计算其他轨道（如35-40），仅需修改showorb.txt并再次运行。
- VMD目录下将保留所有计算过的cube文件，均可通过orb命令调用。

---

## 20. 常见错误：文件读取失败

在VMD中输入orb命令提示无法读取cube文件时，应检查VMD目录下是否存在该文件。
- 可能原因包括VMD路径错误、输入文件格式不对、路径含空格未加引号、轨道序号未包含在范围内、系统权限限制或VMD版本bug。

---

## 21. 常见错误：无效命令

在VMD中输入orb命令提示invalid command name时，通常是VMD未正确加载绘图脚本。
- 需检查vmd.rc是否包含source showorb.vmd并已保存，以及showorb.vmd是否在VMD目录下，修改配置后需重启VMD。
