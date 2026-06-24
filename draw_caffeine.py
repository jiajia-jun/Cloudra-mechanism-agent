#!/usr/bin/env python3
"""
绘制咖啡因 (Caffeine) 高质量分子结构图
使用 RDKit MolDraw2DCairo 生成 PNG
"""

import os
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem.Draw import MolDraw2DCairo

# ── 1. 从 SMILES 构建分子 ──────────────────────────────────
smiles = "CN1C=NC2=C1C(=O)N(C(=O)N2C)C"
mol = Chem.MolFromSmiles(smiles)

if mol is None:
    raise ValueError(f"无法解析 SMILES: {smiles}")

# 生成 2D 坐标（RDKit 自动布局）
AllChem.Compute2DCoords(mol)

print(f"分子: Caffeine (C₈H₁₀N₄O₂)")
print(f"原子数: {mol.GetNumAtoms()}")
print(f"SMILES: {Chem.MolToSmiles(mol)}")

# ── 2. 使用 MolDraw2DCairo 绘制 ───────────────────────────
width, height = 800, 600
drawer = MolDraw2DCairo(width, height)

# 设置绘图选项
opts = drawer.drawOptions()
opts.backgroundColour = (1.0, 1.0, 1.0, 1.0)   # 白色背景 (RGBA)
opts.legendFontSize = 32                         # 图例字体
opts.baseFontSize = 0.7                          # 原子标签相对大小
opts.bondLineWidth = 5                           # 键线宽
opts.multipleBondOffset = 0.18                   # 双键间距
opts.padding = 0.08                              # 留白比例
opts.clearBackground = True
opts.addAtomIndices = False                      # 不显示原子编号
opts.addStereoAnnotation = True                  # 显示手性标注
opts.includeAtomTags = False
opts.circleAtoms = False                         # 不在原子周围画圈
opts.atomLabelDeuteriumTritium = True
opts.legendFraction = 0.12                       # 图例区域占比

# 绘制分子（标题显示为 legend）
drawer.DrawMolecule(mol, legend="Caffeine")

# 完成绘制并获取 PNG 数据
drawer.FinishDrawing()
png_data = drawer.GetDrawingText()

# ── 3. 保存 PNG ───────────────────────────────────────────
output_path = "/home/yyy2333/Cloudra/program/CLOUDRA/caffeine.png"
os.makedirs(os.path.dirname(output_path), exist_ok=True)

with open(output_path, "wb") as f:
    f.write(png_data)

file_size = os.path.getsize(output_path)
print(f"\n✅ 图片已保存: {output_path}")
print(f"   文件大小: {file_size:,} bytes")
print(f"   尺寸: {width}×{height} px")
