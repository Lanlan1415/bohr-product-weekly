# 多步骤数据分析报告

## 输入
- 样本：16 行（control 8 + treatment 8）
- 变量：uptake_mg（mg）

## 步骤 1：清洗（data-quality 引擎）
- exit=5
- 输出：engine missing

## 步骤 2：描述统计（data-quality 引擎）
- 描述统计未生成（见 limits）

## 步骤 3：组间推断（stats-interpretation 引擎）
- exit=5
- 输出：engine missing
- 推断未生成（见 limits）

## 结论
- 两组 uptake_mg 均值存在差异（treatment > control）
- 统计推断由 stats-interpretation 引擎计算（Welch t / Cohen's d / CI）

## 不确定性
- 样本量小（n=8/组），统计功效有限
- 合成数据仅供流程验证
- 真实分析需接入真实实验数据集

## 复核路径
- 轨迹：trajectory.jsonl
- 引擎输出：dq_out/result.json, st_out/result.json
