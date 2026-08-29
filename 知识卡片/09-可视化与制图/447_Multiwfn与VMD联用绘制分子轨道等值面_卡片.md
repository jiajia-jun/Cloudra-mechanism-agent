---
id: 447
title: 使用Multiwfn+VMD快速绘制高质量分子轨道等值面图（含视频）
domain: 可视化与制图
topic: Multiwfn与VMD联用绘制分子轨道等值面
cards: 13
---

## 1. 绘制分子轨道的Multiwfn与VMD联用方法
- Multiwfn官网
- VMD版本：1.9.3
可参考《使用Multiwfn观看分子轨道》一文。

---

## 2. 脚该资料件准备与配置步骤
将Multiwfn文件包examples\scripts目录下的showorb.bat和showorb.txt拷贝到Multiwfn可执行文件所在目录。编辑showorb.bat，将其中的输入文件名改为实际文件名（如1.fch），并将VMD路径修改为实际路径（若路径含空格需加双引号）。编辑showorb.txt，将第三行设为要绘制的轨道序号范围（格式如10,20-23,28-30）。
- 命令行示例：move /Y *.cub "D:\study\VMD 193"

---

## 3. VMD绘图脚本的加载与自定义命令
将VMD绘图脚本showorb.vmd拷贝到VMD目录下，并在VMD目录下的vmd.rc文件末尾插入命令：source showorb.vmd。VMD启动后会自动执行该脚本，定义orb、orbiso、orbclean三个命令，可在VMD文本窗口输入使用以控制轨道载入、显示和清理。
- 定义命令：source showorb.vmd

---

## 4. VMD文本窗口中的orb命令功能
orb命令用于载入和显示轨道，输入orb [序号]即可载入对应序号的cube文件并以等值面形式显示。例如输入orb 33会载入orb000033.cub；再次输入orb 34时会撤销33号轨道并显示34号轨道。默认显示的轨道等值面数值为0.05，可通过编辑showorb.vmd修改。
- 命令示例：orb 33

---

## 5. VMD文本窗口中的orbiso和orbclean命令
orbiso命令用于修改当前显示的轨道等值面数值，例如输入orbiso 0.02会将等值面数值设为0.02。orbclean命令用于删除VMD目录下所有orb开头的.cub文件，防止文件堆积。
- 命令示例：orbiso 0.02

---

## 6. 使用showorb.bat自动计算并生成cube文件
完成准备工作后双击showorb.bat，脚本将调用Multiwfn计算指定轨道的格点数据并导出为cube文件。生成的cube文件（如orb000020.cub）会自动移动到VMD目录下，VMD目录下出现相应文件即表示运行成功。之后启动VMD即可使用orb命令查看轨道。
- 文件命名规则：orb[轨道序号].cub

---

## 7. NH2-biphenyl-NO2体系绘制实例
将examples\excit目录下的D-pi-A.fchk拷贝至Multiwfn目录并改名为1.fch。将showorb.txt第三行改为54-59以考察HOMO-2到LUMO+2轨道。运行showorb.bat后启动VMD，输入orb 56查看HOMO，输入orb 57查看LUMO，正负相位分别以红蓝色显示。
- HOMO序号：56
- 考察范围：54-59

---

## 8. 非限制性开壳层波函数的Beta轨道选择
对于非限制性开壳层波函数，Beta轨道序号排在Alpha轨道之后。若体系有x个基函数，第1号Beta轨道在Multiwfn中的序号为x+1。修改showorb.txt时需据此设定范围，也可在Multiwfn主功能0界面输入负号加轨道号（如-30）查看特定Beta轨道的序号。
- 序号计算：Beta序号 = Alpha基函数数 + Beta轨道号

---

## 9. 分子轨道绘图的格点质量与延展距离设置
脚本默认使用中等质量格点（总点数约512000个），对于100原子以上的大体系建议将showorb.txt第四行的2改为3以提高质量。对于里德堡轨道，为防止等值面被截断，应在showorb.txt第三行和第四行之间插入"-10"和"12"，将延展距离加大到12 Bohr。
- 大体系设置：将质量参数2改为3
- 里德堡轨道设置：插入 -10 和 12

---

## 10. 分子轨道绘图的材质与颜色调整
默认等值面显示材质为Glossy，透明材质推荐EdgyGlass或Translucent，可在VMD图形界面Graphics - Representation中修改或编辑showorb.vmd替换材质名。默认正负相位颜色为红（正）蓝（负），可在Graphics - Representation界面修改Color ID值，或编辑showorb.vmd中的ColorID。
- 材质推荐：EdgyGlass, Translucent

---

## 11. 使用Tachyon渲染器提升图像质量
建议使用Tachyon渲染器进行渲染以获得抗锯齿效果和更好的材质显示效果。Tachyon的使用方法可参考《用Multiwfn+VMD做RDG分析时的一些要点和常见问题》。使用EdgyGlass或Translucent材质时，渲染与直接在图形窗口查看的效果差异明显。

---

## 12. VMD报错“Could not read file”的排查方法
若VMD提示无法读取orb文件，可能原因包括：VMD路径错误或未加引号；输入文件格式不对；输入文件路径错误；轨道序号范围未包含目标轨道；VMD装在C盘因权限问题导致文件未移动；VMD版本有bug（推荐使用1.9.3版）。
- 推荐版本：VMD 1.9.3

---

## 13. VMD报错“invalid command name”的排查方法
若VMD提示命令无效，可能原因包括：vmd.rc文件未写入source showorb.vmd；vmd.rc文件未保存或保存后未重启VMD；showorb.vmd文件未放在VMD目录下导致无法自动运行。
- 必需操作：在vmd.rc中写入 source showorb.vmd 并重启VMD
