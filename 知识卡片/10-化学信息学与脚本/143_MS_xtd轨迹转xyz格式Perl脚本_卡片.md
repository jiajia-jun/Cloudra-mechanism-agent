---
id: 143
title: 将Material Studio的xtd轨迹文件导出为xyz轨迹文件的方法
url: http://sobereva.com/143
domain: 化学信息学与脚本
topic: MS_xtd轨迹转xyz格式Perl脚本
cards: 3
---

# MS_xtd轨迹转xyz格式Perl脚本 — 知识卡片

## 1. xtd文件与.trj文件的关系

Material $tudio的xtd文件包含原子或粗粒化模拟中bead的轨迹信息，这是MS的私有格式。xtd文件内含的实际轨迹信息实际储存在同目录下同名的.trj隐藏文件里（二进制文件）。

## 转换xtd轨迹的Perl脚本思路
利用MS内部支持的Perl脚本，循环读取每一帧每一个原子或Bead，将其坐标属性按照xyz格式写入到外部文本文件，即可生成能被VMD等程序直接载入的xyz轨迹。

## 全原子轨迹转换脚本xtd2xyz
此脚本用于将MS全原子模拟（如Forcite）的xtd轨迹转换为xyz格式，原作者为Andrea Minoia，由Sobereva修改并加入了对周期性体系的支持。脚本文件后缀需为.pl，使用前需修改变量`$doc`中的文件名，并通过F5或菜单运行。

## xtd2xyz脚本核心参数设置
脚本中`my $framebegin=1;`和`my $frameend=$trajectory->NumFrames;`定义了转换的帧数范围。若需转换指定帧数，需取消注释并修改`my $frameend=10;`为自定的起止帧号。

## xtd2xyz脚本运行模式与输出位置
在MS中通过tools-scripting-debug运行脚本转换大体系较慢，通过tools-scripting-Run on server模式运行速度更快。转换结束后输出文件名为trj.txt，将后缀改为.xyz即可被VMD读取；服务器模式下trj.txt及当前目录其他文件会被复制到新目录。

## 周期性体系轨迹转换注意事项
对于周期性体系，转换出的轨迹样式与MS中的显示设置一致。在Display style-Lattice中某个方向上多显示一个周期，转换出的轨迹在相应方向也会多出一倍原子；Default、In-Cell、Original显示模式下的转换坐标也会相应不同。

## 粗粒化轨迹转换脚本xtdbead2xyz
xtdbead2xyz脚本专门用于转换粗粒化模拟（如Mesocite）中以bead描述粒子的xtd轨迹，不能转换全原子轨迹。脚本中获取粒子的方式为`my $Beads = $doc->DisplayRange->Beads;`，写入内容为`$Bead->Name`和坐标。

---

## 2. xtd2xyz脚本代码

```perl
#!perl
  #**********************************************************
  #* *
  #* XTD2XYZ - Convert XTD files into XYZ ormat *
  #* *
  #**********************************************************
  # Version: 0.1
  # Author: Andrea Minoia
  # Date: 08/09/2010
  #
  # Convert MS trajectory xtd file into xYZ trajectory file.
  # Backup of files that are about to be overwritten is managed
  # by MS. The most recent file is that with higher index number (N)
  # The script has to be in the same directory of the
  # structure to modify and the user has to update the
  # variable $doc (line 31) according to the name of the
  # file containing the trajectory.
  # The xmol trajectory is stored in trj.txt file and it is not
  # possible to rename the file within MS, nor it is possible to
  # automatically export it as xyz or car file. You should manage
  # the new trajectory manually for further use (e.g. VMD)
  #
  # Modificator: Sobereva (sobereva@sina.com)
  # Date: 2012-May-23
  # The range of the frames to be outputted can be altered by line 49 and 51

use strict;
  use MaterialsScript qw(:all);

#open the multiframe trajectory structure file or die
  my $doc = $Documents{"./benzene.xtd"};

if (!$doc) {die "no document";}

my $trajectory = $doc->Trajectory;

if ($trajectory->NumFrames>1) {

print "Found ".$trajectory->NumFrames." frames in the trajectory\n";
  # Open new xmol trajectory file
  my $xmolFile=Documents->New("trj.txt");

  #get atoms in the structure
  # my $atoms = $doc->Atoms;
  my $atoms = $doc->DisplayRange->Atoms;
  my $Natoms=@$atoms;

  my $framebegin=1;
  my $frameend=$trajectory->NumFrames;
  # my $frameend=10;
  for (my $frame=$framebegin; $frame<=$frameend; ++$frame){
  $trajectory->CurrentFrame = $frame;
  #write header xyz
  $xmolFile->Append(sprintf "%i \n", $Natoms);
  $xmolFile->Append(sprintf "%s %i \n", "Frame",$frame);
  foreach my $atom (@$atoms) {
  # write atom symbol and x-y-z- coordinates
  $xmolFile->Append(sprintf "%s %f %f %f \n",$atom->ElementSymbol, $atom->X, $atom->Y, $atom->Z);
  }
  }
  #close trajectory file
  $xmolFile->Close;
  }
  else {
  print "The " . $doc->Name . " is not a multiframe trajectory file \n";
  }
```

---

## 3. xtdbead2xyz脚本代码

```perl
#!perl
 # XTDbead2XYZ - Convert the XTD files containing beads into XYZ format
 # Creator: Sobereva (sobereva@sina.com)
 # Date: 2012-May-23

use strict;
 use MaterialsScript qw(:all);

#open the multiframe trajectory structure file or die
 my $doc = $Documents{"./bilayer.xtd"};

if (!$doc) {die "no document";}

my $trajectory = $doc->Trajectory;

if ($trajectory->NumFrames>1) {

print "Found ".$trajectory->NumFrames." frames in the trajectory\n";
  # Open new xmol trajectory file
  my $xmolFile=Documents->New("trj.txt");

  #get atoms in the structure
  my $Beads = $doc->DisplayRange->Beads;
  my $NBeads=@$Beads;

  my $framebegin=1;
  my $frameend=$trajectory->NumFrames;
 # my $frameend=10;
  for (my $frame=$framebegin; $frame<=$frameend; ++$frame){
  $trajectory->CurrentFrame = $frame;
  #write header xyz
  $xmolFile->Append(sprintf "%i \n", $NBeads);
  $xmolFile->Append(sprintf "%s %i \n", "Frame",$frame);
  foreach my $Bead (@$Beads) {
  # write atom symbol and x-y-z- coordinates
  $xmolFile->Append(sprintf "%s %f %f %f \n",$Bead->Name, $Bead->X, $Bead->Y, $Bead->Z);
  }
  }
  #close trajectory file
  $xmolFile->Close;
 }
 else {
  print "The " . $doc->Name . " is not a multiframe trajectory file \n";
 }
```
