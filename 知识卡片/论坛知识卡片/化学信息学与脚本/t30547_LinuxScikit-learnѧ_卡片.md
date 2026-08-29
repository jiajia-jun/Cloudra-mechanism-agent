---
key: t30547
title: Linux��Scikit-learn����ѧϰʵ���ű�
url: http://bbs.keinsci.com/thread-30547-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2022
cards: 6
---

# Linux��Scikit-learn����ѧϰʵ���ű� — 知识卡片

## 1. 基于Scikit-learn的机器学习脚件结构 (Models文件夹)

Models文件夹包含用于连续变量预测的机器学习脚本，文件按功能分为模型训练、模型保存、预测应用、数据集及汇总脚本。该文件夹中的模型训练脚本通常使用 `_CUTLOSS.py`、`_MA100.py` 和 `_TAND.py` 等命名。模型文件以 `.pkl` 格式保存，包括经过网格搜索优化的模型 (`*_GS.pkl`) 和最佳模型 (`*_best.pkl`)。预测脚本 `ML_prediction.py` 需调用优化后的 `.pkl` 模型文件。数据集文件 `1502_LYL.csv` 用于提供连续变量的训练数据。

---

## 2. 基于Scikit-learn的机器学习脚件结构 (Models2文件夹)

Models2文件夹包含针对离散变量预测的机器学习脚本，文件命名反映了不同的移动平均或特征处理方式。该文件夹下的模型训练脚本包括 `Hardness_*.py`、`MA10_*.py`、`MA100_*.py`、`MA300_*.py` 和 `pd_*.py`。模型优化结果保存在 `*_best.pkl` 文件中。预测脚本 `ML_predictions_find_best.py` 采用枚举法计算每个离散变量的结果以寻找最优预测。

---

## 3. 连续变量预测流程与脚本功能

连续变量预测流程涉及模型训练、保存、预测及结果汇总的自动化。`folder_pred_all.sh` 是执行预测的脚本，调用 `ML_prediction.py` 进行计算，预测信息输出至 `Extract_sklearn_predictions.txt`。`Extract_sklearn.sh` 是汇总训练信息的脚本，处理后的训练结果保存在 `Extract_sklearn_results.txt`。数据集 `1502_LYL.csv` 作为连续变量的输入数据源。

---

## 4. 离散变量预测流程与脚本功能

离散变量预测流程通过枚举法处理预测结果以寻找最佳匹配。数据集 `TZ038-41.csv` 提供离散变量数据。`folder_pred_find_best_all` 脚本用于运行预测程序 `ML_predictions_find_best.py`，预测信息被记录在 `Extract_sklearn_predictions_find_best.txt` 中。训练信息汇总同样使用 `Extract_sklearn.sh` 脚本，结果输出至 `Extract_sklearn_results.txt`。

---

## 5. Pipeline与GridSearchCV的应用

模型训练脚本基于 Pipeline（管道）和 GridSearchCV（网格搜索）构建。Pipeline 用于将数据预处理和模型训练步骤封装在一起，GridSearchCV 用于在数据集上进行超参数优化以寻找最佳超参数组合。该方法适用于自动寻找最优超参数并生成预测。关于 Pipeline 和 GridSearchCV 的详细定义可参考 Scikit-learn 官方文档。

---

## 6. 模型解释工具SHAP

模型分析可结合 SHAP 工具在 Linux 环境下进行交互式解释。SHAP 用于对机器学习模型的计算结果进行解释分析。相关的操作指南和讨论可在特定技术论坛的专题帖中查阅。
