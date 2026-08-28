---
id: 182
title: 利用wfn文件计算电子密度的代码的编写方法
url: http://sobereva.com/182
domain: 波函数与电子结构分析
topic: 基于wfn文件计算电子密度的Fortran代码
cards: 10
---

# 基于wfn文件计算电子密度的Fortran代码 — 知识卡片

## 1. 程序结构与模块定义

程序包含module defvar定义全局变量和类型，module function包含计算子程序，program wfnprop为交互主程序，readwfn子程序用于读取wfn文件，uc2lc和lc2uc用于字符大小写转换。type atomtype定义了原子名、序号、坐标和核电荷数，type primtype定义了高斯函数所属中心、类型和指数。name2ind数组存储了原子名到原子序号的映射表，type2ix/y/z数组存储了GTF类型到x,y,z指数的映射。
- `integer :: type2ix(35)=(/ 0,1,0,0, 2,0,0,1,1,0, 3,0,0,2,2,0,1,1,0,1, 0,0,0,0,0,1,1,1,1,2,2,2,3,3,4 /)`
- `integer :: type2iy(35)=(/ 0,0,1,0, 0,2,0,1,0,1, 0,3,0,1,0,2,2,0,1,1, 0,1,2,3,4,0,1,2,3,0,1,2,0,1,0 /)`
- `integer :: type2iz(35)=(/ 0,0,0,1, 0,0,2,0,1,1, 0,0,3,0,1,1,0,2,2,1, 4,3,2,1,0,3,2,1,0,2,1,0,1,0,0 /)`

---

## 2. orbderv子程序的功能与参数

orbderv子程序用于计算指定位置所有轨道的波函数数值及其导数，runtype=1时仅计算数值，runtype=2时计算数值和导数，istart和iend指定轨道范围。程序通过循环每个高斯函数并累加其对所有轨道的贡献来提高效率，而非循环每个轨道。高斯函数值计算公式为 $N x^{l_x} y^{l_y} z^{l_z} e^{-\varepsilon r^2}$，其中 $\varepsilon$ 为指数，坐标为相对于所属原子核的坐标。
- `subroutine orbderv(runtype,istart,iend,x,y,z,wfnval,grad)`
- `real*8 x,y,z,wfnval(nmo)`
- `real*8,optional :: grad(3,nmo)`

---

## 3. 高斯函数导数的计算代码

在orbderv子程序中，当runtype==2时计算高斯函数在x,y,z方向的导数，GTFdx、GTFdy、GTFdz分别代表当前GTF在三个方向的导数值。计算利用了幂函数的导数规则和指数函数的链式法则，并将导数值乘以轨道展开系数累加到grad数组中。最终轨道波函数导数由所有基函数贡献累加得到。
- `GTFdx=sfty**iy *sftz**iz *expterm*(tx-2*ep*sftx**(ix+1))`
- `GTFdy=sftx**ix *sftz**iz *expterm*(ty-2*ep*sfty**(iy+1))`
- `GTFdz=sftx**ix *sfty**iy *expterm*(tz-2*ep*sftz**(iz+1))`

---

## 4. 电子密度计算函数fdens

fdens函数通过调用orbderv获取指定位置的轨道波函数值，然后将每个轨道的波函数值的平方乘以轨道占据数并累加，得到该点的总电子密度。代码适用于实函数波函数，因此模方等于平方。该函数可以方便地移植到用户自己的程序中调用。
- `real*8 function fdens(x,y,z)`
- `fdens=fdens+MOocc(i)*wfnval(i)**2`

---

## 5. readwfn子程序的文件读取流程

readwfn子程序首先读取wfn文件的标题行、轨道数、基函数数和原子数，然后分配数组内存。接着循环读取原子信息（名称、坐标、电荷）并转换原子名大小写以匹配原子序号。随后读取基函数的中心、类型、指数，以及每个轨道的占据数、能量和展开系数。最后根据读取的数据进行后续处理。
- `read(10,"(8x,i15,13x,i7,11x,i9)") nmo,nprims,ncenter`
- `read(10,"(a24,3f12.8,10x,f5.1)") c80tmp,a(i)%x,a(i)%y,a(i)%z,a(i)%charge`
- `read(10,"(5D16.8)") (CO(i,j),j=1,nprims)`

---

## 6. 波函数类型的自动判定逻辑

程序根据轨道占据数的特征自动判定波函数类型：若占据数之和等于2倍轨道数则为RHF/RKS（wfntype=0）；若等于轨道数则为UHF/UKS（wfntype=1）；若存在非整数占据数则为后HF波函数；否则为ROHF/ROKS（wfntype=2）。对于后HF波函数，若最大占据数接近2则为闭壳层（wfntype=3），否则为开壳层（wfntype=4）。对于UHF和开壳层后HF，程序会依据能量或占据数的变化点区分alpha和beta轨道。
- `if (sum(MOocc)==2*nmo) wfntype=0`
- `else if (sum(MOocc)==nmo) wfntype=1`
- `else if (any(MOocc/=int(MOocc))) wfntype=3 or 4`

---

## 7. 电子数统计与输出信息

程序遍历所有轨道，根据轨道类型累加alpha和beta电子数，alpha/beta电子数之和为总电子数。程序随后输出总电子数、Alpha电子数、Beta电子数、净电荷、期望自旋多重度、轨道数、原子数、基函数数以及波函数类型描述。这些信息用于用户确认wfn文件读取和解析的正确性。
- `write(*,"('Total/Alpha/Beta electrons:',3f12.4)") nelec,naelec,nbelec`
- `write(*,"('Net charge:',f12.5,' Expected multiplicity:',i5)") sum(a(:)%charge)-nelec,nint(naelec-nbelec)+1`

---

## 8. 自旋密度计算函数fspindens

fspindens函数计算指定位置的自旋密度，即alpha电子密度减去beta电子密度。该函数调用orbderv获取轨道波函数，然后根据MOtype数组区分alpha和beta轨道，分别计算其密度贡献。最终返回两者的差值，可用于分析分子的自旋分布。
- `real*8 function fspindens(x,y,z)`
- `fspindens=adens-bdens`

---

## 9. 电子密度导数计算函数fgrad

fgrad函数计算电子密度在x、y、z方向的导数或梯度的模，由参数label指定返回值类型。函数调用orbderv获取轨道波函数及其一阶导数，根据公式 $\nabla \rho = 2 \sum_i n_i \phi_i \nabla \phi_i$ 计算密度梯度。若label为't'，则返回梯度的模长 $\sqrt{(\partial \rho/\partial x)^2 + (\partial \rho/\partial y)^2 + (\partial \rho/\partial z)^2}$。
- `real*8 function fgrad(x,y,z,label)`
- `gradrho(:)=gradrho(:)+MOocc(i)*wfnval(i)*wfnderv(:,i)`
- `gradrho=2*gradrho`

---

## 10. 代码使用引用说明

本文提供的代码源自Multiwfn 3.0并进行了精简，若需更强的功能、更快的速度或更好的兼容性，应直接提取Multiwfn源码中的完整子程序。如果读者在自行开发的程序中使用了本文代码或Multiwfn的代码并打算发表文章，必须引用Multiwfn的原始文献。代码文件可从博文提供的链接下载，并在CVF6.5、Intel Visual Fortran上编译通过。
- 引用文献: Tian Lu, Feiwu Chen, J. Comp. Chem. 33, 580-592 (2012)
