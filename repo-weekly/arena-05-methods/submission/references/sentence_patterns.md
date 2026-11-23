# 中英双语步骤句式模板库（写作09）

按六类要素组织。`{占位符}` 必须从材料取值并挂 `[S#]`；**禁止为套用句式补造材料中没有的内容**。中英条目一一对应，双语任务中同一事实两种语言的数值、单位、版本号必须逐字一致。

## 1. 实验设置（Experimental Setup）

### 1.1 硬件与环境
- 中：所有实验在 `{硬件型号与数量}` 上完成，操作系统为 `{OS 版本}`，使用 `{框架} {版本}`（CUDA `{版本}`）实现。[S#]
- EN：All experiments were conducted on `{hardware, e.g., 4× NVIDIA A100 80GB GPUs}` running `{OS version}`, implemented with `{framework} {version}` (CUDA `{version}`). [S#]

### 1.2 随机性与重复
- 中：除特别说明外，所有结果为 `{n}` 次独立运行（随机种子 `{seeds}`）的均值 ± 标准差。[S#]
- EN：Unless otherwise stated, all results are reported as the mean ± standard deviation over `{n}` independent runs (random seeds `{seeds}`). [S#]
- 材料只跑了一次时：
- 中：受计算资源限制，本节结果为单次运行结果，随机种子固定为 `{seed}`。[S#]
- EN：Due to computational constraints, the results in this section are from a single run with random seed fixed to `{seed}`. [S#]

### 1.3 代码与依赖
- 中：代码基于 `{仓库/版本或 commit}`，完整依赖见 `{requirements.txt / 环境文件}`。[S#]
- EN：Our implementation builds upon `{repository/version or commit}`; the full dependency list is available in `{requirements file}`. [S#]

## 2. 步骤（Procedure）——每步一句，含输入/操作/输出/判断条件

### 2.1 顺序连接词
- 中：首先……；随后……；接着……；最后……。（避免"然后……然后……"连用）
- EN：First, ...; next, ...; subsequently, ...; finally, ....

### 2.2 单步句式（操作+对象+条件+时长/阈值）
- 中：将 `{对象}` 置于 `{条件}` 下 `{操作}` `{时长/次数}`，直至 `{判断条件}`。[S#]
- EN：`{Object}` was/were `{operation}` under `{condition}` for `{duration/iterations}` until `{termination criterion}`. [S#]
- 中：对 `{输入}` 依次进行 `{预处理步骤1}`、`{步骤2}` 与 `{步骤3}`，得到 `{输出}`（`{规模/形状}`）。[S#]
- EN：The `{input}` was sequentially `{step 1}`, `{step 2}`, and `{step 3}`, yielding `{output}` (`{size/shape}`). [S#]

### 2.3 判断条件句式（把"至收敛"写实）
- 中：当 `{监控指标}` 连续 `{k}` 轮下降幅度小于 `{阈值}` 时停止训练（早停）。[S#]
- EN：Training was early-stopped when `{monitored metric}` failed to improve by at least `{threshold}` for `{k}` consecutive epochs. [S#]
- 中：若 `{异常条件}`，则丢弃该批次并重新采样，重复次数不超过 `{n}` 次。[S#]
- EN：If `{failure condition}`, the batch was discarded and resampled, at most `{n}` times. [S#]

## 3. 参数（Parameters）

### 3.1 参数表指引句
- 中：全部超参数及其取值、单位与来源汇总于表 `{编号}`；正文仅引用该表，不再重复列值。
- EN：All hyperparameters, together with their values, units, and sources, are summarized in Table `{n}`; the text refers to this table rather than repeating values.

### 3.2 正文引用句式（值必须逐字等于参数表）
- 中：模型采用 `{优化器}` 优化，学习率为 `{值}`，批大小为 `{值}`，训练 `{轮数}` 轮。[S#]
- EN：The model was optimized with `{optimizer}` at a learning rate of `{value}` and a batch size of `{value}` for `{epochs}` epochs. [S#]
- 中：`{参数}` 沿用 `{框架}` 默认值 `{值}`（代码未另行设置 [S#]）。
- EN：`{Parameter}` followed the `{framework}` default of `{value}` (not overridden in the code [S#]).

### 3.3 参数搜索（材料有调参记录时）
- 中：`{参数}` 在 `{候选集合/区间}` 中按 `{搜索方式}` 选取，以 `{验证集指标}` 为准。[S#]
- EN：`{Parameter}` was selected from `{candidate set/range}` via `{search strategy}` according to `{validation metric}`. [S#]

## 4. 数据集与划分（Datasets and Splits）

- 中：实验使用 `{数据集名}`（版本 `{版本/获取日期}`，共 `{规模}` 条）[S#]。原始数据经 `{预处理}` 后，按 `{比例}` 随机划分为训练/验证/测试集（随机种子 `{seed}`）[S#]。
- EN：We used `{dataset}` (version `{version/access date}`, `{size}` samples) [S#]. After `{preprocessing}`, the data was randomly split into training/validation/test sets with a ratio of `{ratio}` (random seed `{seed}`) [S#].
- 中：划分在样本级/患者级/时间维度进行，{防止泄漏的说明}。[S#]
- EN：The split was performed at the `{sample/patient/time}` level; `{leakage-prevention note}`. [S#]
- 版本不明时（不写死）：
- 中：材料未注明 `{数据集}` 的具体版本，待作者确认后补充。
- EN：The exact version of `{dataset}` is not specified in the materials and awaits author confirmation.

## 5. 对照与统计（Baselines and Statistics）

### 5.1 基线
- 中：选取 `{基线1}`（`{版本/出处}`）与 `{基线2}`（`{版本/出处}`）作为对照；所有方法在相同数据划分与 `{预算说明}` 下比较。[S#]
- EN：We compared against `{baseline 1}` (`{version/source}`) and `{baseline 2}` (`{version/source}`); all methods were evaluated on identical data splits under `{budget note}`. [S#]
- 基线非同预算时（如实写）：
- 中：`{基线}` 的结果引自原文 [S#]，其训练设置（`{差异}`）与本文不完全一致，比较仅供参考。
- EN：Results for `{baseline}` are quoted from the original paper [S#]; its training setup (`{difference}`) differs from ours, and the comparison is indicative only.

### 5.2 指标与显著性
- 中：以 `{指标}`（`{定义或出处}`）为主要评价指标；采用 `{检验方法}` 检验差异显著性，显著性水平取 `{α}`。[S#]
- EN：`{Metric}` (`{definition or citation}`) served as the primary evaluation metric; significance was assessed with `{test}` at `{α}`. [S#]

## 6. 复现与限制（Reproducibility and Limitations）

- 中：复现所需的代码、环境、命令与数据获取方式汇总于附录 `{编号}`/表 `{编号}`。
- EN：The code, environment, commands, and data-access instructions required for reproduction are summarized in Appendix `{n}` / Table `{n}`.
- 限制（落到具体场景，禁套话）：
- 中：当 `{具体场景}` 时，本方法 `{失效表现}`（依据：`{材料/日志位置}`）；因此适用范围限于 `{范围}`。[S#]
- EN：Under `{specific scenario}`, the method `{failure mode}` (evidence: `{material/log location}` [S#]); its applicable scope is therefore limited to `{scope}`.
- 待确认（统一格式）：
- 中：[待确认：`{缺口}`，需作者提供 `{具体材料}`]
- EN：[To be confirmed: `{gap}`; requires `{specific material}` from the authors]

## 7. 使用禁忌

1. 句式是骨架不是答案：占位符没有材料支撑时，整句不得出现，改用 §6 的待确认句式；
2. 不在英文句式里夹中文数值格式（如"1万"），不在中文句式里夹未翻译的英文术语而不给全称；
3. 同一句式不要在相邻段落重复三次以上，步骤列表优先于散文句式。
