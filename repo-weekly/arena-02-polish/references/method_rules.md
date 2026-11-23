# 方法细则：守恒规则、四级润色与判定标准（学术语言润色）

## 目录

1. 守恒规则（红线，先读后改）
2. L1 语法级：判定标准与示例
3. L2 句式级：判定标准与示例
4. L3 风格级：判定标准与示例
5. L4 逻辑连贯级：判定标准与示例
6. 不确定改法的备选机制
7. 反模式（写了等于没写）
8. 锚定协议与编辑记录（v2，流水线核心）

---

## 1. 守恒规则（红线，先读后改）

以下五类内容润色前后必须**逐字一致**，由 `verify.py`（句级，逐条编辑）与
`conservation_check.py`（整文档，复核）双重强制：

| 守恒对象 | 说明 | 典型翻车 |
|---|---|---|
| 数字与数值 | 含小数、千分位、科学计数、百分号；"25 °C"→"room temperature" 也算改数字 | 顺手四舍五入、改单位制、约数精确化 |
| 术语表内术语 | terms.txt 批准写法的出现次数不变；统一术语只能把**未批准写法**改成批准写法 | "LLZO"被改成"garnet electrolyte"后术语链断裂 |
| 引用标记 | [12]、[3-5]、[S2]、（作者, 年份） | 重排编号、合并引用、漏引 |
| 图表/公式编号 | Figure 1、Table 2、Eq. (3)、图1、表2、式(3) | "Figure 1"→"Figure 2"式笔误 |
| 公式 | LaTeX 行内/行间公式逐字符 | 顺手"化简"公式、改上下标 |

另有两类**软守恒**——在 v2 流水线中已升级为句级硬门（verify.py 计数变化
即回退）；整文档级的 `conservation_check.py` 仍按 WARN 处理、人工逐处核对：

- **限定强度**：may/might/suggest/indicate/approximately、可能/约/有望——不得加强（may→demonstrate）也不得削弱（show→suggest）；分级与同级替换规则见 `references/qualifier_lexicon.md`；
- **结论方向与否定范围**：否定词计数变化必有核对记录；"not significantly affect" 不可润成 "barely affect"。

唯一合法例外：任务书/期刊要求/作者书面确认明确规定的改动（如统一 SI 单位、
作者确认可直陈）。例外必须：编辑记录带 `allow_conservation_break: true` +
`reason`，并在 change_log 写"有意为之 + 依据出处"。

## 2. L1 语法级：判定标准与示例

原则：**只修硬错误，编辑量最小**。

| 类型 | 改前 | 改后 | 理由 |
|---|---|---|---|
| 主谓一致 | The electrolyte have attracted… | The electrolyte has attracted… | 主语单数 |
| 时态 | The conductivity was measured and reaches 3.2e-4 S/cm | …was measured and reached 3.2e-4 S/cm | 同一实验叙述时态一致（过去时）；数值不动 |
| 冠词 | LLZO is promising candidate | LLZO is a promising candidate | 可数名词单数缺冠词 |
| 单复数 | This results suggest | These results suggest | 指示代词与名词数一致 |
| 悬垂修饰 | Using EIS, the impedance was measured | Using EIS, we measured the impedance | 分词逻辑主语须与主句主语一致 |
| 标点（中文） | 结果表明，该材料性能优异,且稳定性良好 | 结果表明，该材料性能优异，且稳定性良好 | 逗号全半角统一 |

判定为"硬错误"才动手："the data shows"（口语可接受）这类争议项不属硬错误，标【备选】。

## 3. L2 句式级：判定标准与示例

原则：**改结构不改信息分配**——切分长句时每个从句的限定功能必须保留。

| 类型 | 改前 | 改后 | 理由 |
|---|---|---|---|
| 长句切分 | The conductivity, which was measured by EIS at 25 °C using blocking electrodes, reaches 3.2e-4 S/cm. | The conductivity was measured by EIS at 25 °C using blocking electrodes. It reaches 3.2e-4 S/cm. | 一句一义；条件（EIS、25 °C、blocking electrodes）全部保留 |
| 中式语序 | 我们 widely 使用了…式语序：We in this work used… | In this work, we used… | 状语归位 |
| 冗余名词化 | The measurement of the conductivity was carried out by us | We measured the conductivity | 动词化，主语明确 |

反例（禁止）：把 "may, under certain conditions, improve" 切分成两句后条件状语丢失——信息分配变了，属于改坏。

## 4. L3 风格级：判定标准与示例

原则：**语域对齐目标文体；术语按 terms.txt 统一；编辑量仍最小**。

| 类型 | 改前 | 改后 | 理由 |
|---|---|---|---|
| 去口语化 | The material is super stable. | The material exhibits high stability. | 期刊语域；但 "may be stable" 里的 may 不许动 |
| 去宣传化 | Our groundbreaking method… | Our method…（或 a novel method，若原文有新意表述依据） | 绝对化/宣传化表述违反期刊规范 |
| 去绝对化 | This proves that… | This indicates that… | prove 超出证据强度——但仅限原文本就夸大且任务允许时；拿不准给【备选】 |
| 术语统一 | garnet oxide（terms.txt 批准写法 LLZO） | LLZO | 只替换未批准写法，批准写法计数不变 |
| 人称语态 | You can see in Figure 1 | As shown in Figure 1 | 学术文体避免第二人称；Figure 1 编号守恒 |

## 5. L4 逻辑连贯级：判定标准与示例

原则：**只显化已有信息的连接，不补充新论证、不新增过渡结论**。

| 类型 | 改前 | 改后 | 理由 |
|---|---|---|---|
| 衔接显化 | The conductivity is high. The interface resistance remains large. | The conductivity is high; however, the interface resistance remains large. | 两句原文存在转折关系，however 只是显化 |
| 指代明确 | This leads to dendrite growth. | This interfacial instability leads to dendrite growth. | This 指代不明时补出先行词——先行词必须来自上文，不得臆造 |

反例（禁止）：在段末加 "Therefore, LLZO is the most promising electrolyte"——原文没有此结论，属于新增材料外事实。

## 6. 不确定改法的备选机制

满足任一条件即触发备选机制，不得硬改：

- 改法涉及语义判断而非语法（如 "significant" 是否指统计显著）；
- 两种改法对应两种不同含义，原文无法判定作者意图；
- 改动会触碰守恒对象边缘（如术语变体是否在术语表内）。

记录格式：

```
C017【备选】L3 | 原文：The effect is significant.
  候选A（倾向）：The effect is substantial. —— 若指"程度大"
  候选B：保留原文 —— 若指统计显著（p 值语境）
  理由：无法从上下文判定；统计语境下 significant 是术语，不得替换。
```

## 7. 反模式（写了等于没写）

| 反模式 | 为什么不行 | 正确做法 |
|---|---|---|
| 整段重写："润色后如下"然后重写一遍 | 无法逐条回溯，限定词必然丢失 | 分句级最小编辑 + 逐条记录 |
| 修改记录只有"优化了语言表达" | 第三方无法判断该不该改 | 六要素：编号/级别/原文/改后/类型/理由 |
| may → prove、suggest → demonstrate | 限定强度被偷换，结论方向改变 | 软守恒逐处核对；拿不准标【备选】 |
| 25 °C → room temperature | 数字守恒被破坏，条件信息丢失 | 数值与单位逐字保留 |
| 把 [12] 重排成 [11] 以"匹配新顺序" | 引用编号与文献表脱钩 | 引用标记逐字守恒；顺序问题记入待确认项 |
| 顺手把 $\sigma T = A\exp(-E_a/kT)$ "化简" | 公式被篡改 | 公式逐字符守恒，排版问题也不动 |
| 不确定就选一个顺眼的改 | 50% 概率改坏 | 备选机制：候选 + 倾向 + 理由 |
| 术语统一靠记忆逐处替换 | 漏改、改多、改串 | terms.txt + 全文检索 + 守恒门计数复核 |
| 发现原文数据矛盾就直接改数字 | 越权篡改事实 | 数字守恒；矛盾写入 evidence_map 待确认项 |
| 中文稿件按英文语序"优化" | 产出翻译腔中文 | 中文按中文行文规范（见 style_guide §3） |

---

## 8. 锚定协议与编辑记录（v2，流水线核心）

### 8.1 为什么必须先抄原句

Agent 分批产出句级编辑记录时，**每条记录必须先逐字抄原句（`original`），
再写改文（`replacement`）**。`sentence_id` 只是定位索引，抄录的原句才是锚：
verify.py 用空白宽容比对核对"你以为在改的句子"与"实际那句"是否一致，
不一致即拒绝。公开复盘的最贵教训：某 77.7 分方案在 v1.1 把记录改成
"免抄原文只记 sentence_id"，分数从 76.3 跌到 72.3；v1.2 恢复抄原句锚定
后回到 77.7。原因：id 定位无法发现"记录与实际句子的错位"，错误编辑静默
通过。id-only 记录 verify 宽容接受（记 WARN），但这是降级通道，不是常态。

### 8.2 edits.jsonl 记录格式（每行一条 JSON）

```json
{"edit_id": "C001", "sentence_id": "sent-0007", "level": "L1",
 "original": "The electrolyte have attracted much attention [1].",
 "replacement": "The electrolyte has attracted considerable attention [1].",
 "type": "grammar.agreement", "reason": "主语单数；much→considerable 去口语化"}
```

- `sentence_id` 来自 `prepare.py` 生成的 `sentences.tsv`；
- `original` 逐字抄自该句当前文本（同一句话做链式多轮修改时，后续记录
  抄**上一轮改后**的文本）；空白差异宽容，文字差异拒绝；
- `type` 取 `references/edit_types.md` 词表；`level` ∈ L1–L4；
- 有意守恒例外加 `"allow_conservation_break": true` + 充分 `reason`；
- 【备选】条目不投 edits.jsonl，写在 change_log（见 §6），待作者定夺后再投。

### 8.3 回退处置

verify 的回退清单（`rejected_edits.jsonl`）每条必须三选一：① 修正后重投；
② 确属任务/作者要求 → 转有意例外通道并留依据；③ 放弃（原句不动）。
禁止：绕过 verify 直接把被回退的改动写进润色稿——audit 的守恒复核会抓到。
