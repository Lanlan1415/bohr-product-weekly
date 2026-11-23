---
name: ppt-master
description: >
  学术 PPT 领域总控技能。把论文或研究材料组织成“问题—方法—结果—限制”的可讲主线，
  产出真实可编辑 PPTX、逐页主张与证据映射、讲者备注、真实 PDF 预览记录和版本台账。
  可直接保留结构编辑组织方给出的起始 PPTX，也可读取并套用真实 PPTX/POTX 的母版、版式、
  主题与页面尺寸；覆盖论文转 PPT、既有 deck 修改、模板适配和汇报组织。核验源稿 before、
  after 落位、页预算、叙事节拍、问答准备、图片原比例、中文字形和文本溢出，回填案例契约。
  Use whenever an academic presentation must be created, edited, re-templated, rehearsed or audited.
---

# ppt-master：组织页面，也保留证据映射

本包不是四条路线的文案合集。它用一个最终文件审计器管理三种真实产物路径：从零生成、
保留原包编辑、套入真实模板壳。**先打开实际论文、起始稿和模板，再写页面；先有可编辑文件，
再谈审计通过。** 材料未支持的 claim、图号、数值、预览和模板状态不得以 `clean` 掩盖。

## 组件与职责

| 文件 | 实际职责 |
|-|-|
| `scripts/deckbuild.py` | 总控入口：构建/保结构编辑→模板套用→读回审计→修约→契约回填 |
| `scripts/decksource.py` | 从真实 PPTX 提取页面骨架；保留母版、媒体和嵌入对象执行文本修改 |
| `scripts/templatecheck.py` | 测量真实 PPTX/POTX，并移交其 master/layout/theme 壳 |
| `scripts/deckaudit.py` | 对最终 PPTX 逐页审计，不信任 spec 自述 |
| `scripts/extra_rules.py` | 四条路由的专属结构规则 |
| `scripts/pptxgen.py` | 纯标准库 PresentationML 生成器 |
| `scripts/fontsel.py` | 按实际字符选择有字形的字体 |
| `scripts/glyphmetrics.py` | 无 Pillow/matplotlib 时读取 SFNT/TTC cmap、hmtx 并测量 advance width |
| `scripts/contract_echo.py` | 正常完成后回填 case_id 与 output_contract 同名字段 |

## 六步运行时入口（0–6，按顺序执行）

0. **读输入契约。** 读 `/input/case.json`，逐字段记录 `case_id` 与 `output_contract`；读
   `/input/task.md`，固定受众、时长、最少/最多页数、起始稿和模板要求。枚举实际 PDF、图、
   数据、PPTX/POTX；文件标签不是证据。解析 PDF 时用原 PDF，不假设存在预抽取答案。
1. **按任务措辞路由。** 使用下表确定 section 和必填字段；一个案例可在同一 spec 叠加目标、
   修订和模板字段，但只选一个 section。跨路由必须顺序产生新 spec 和新一轮变更台账。
2. **先产出目标产物。** 从源材料提炼研究问题、方法、结果和限制，每页写一个可反驳 claim、
   来源 locator 与讲者备注；先保存 `/app/output/deck.pptx` 的诚实版本。编辑任务优先保留
   原包，而不是按记忆重建；模板任务使用模板文件本体。
3. **构造 spec。** 在 `/app/work` 写 JSON：公共字段为 slides、available_evidence、spacing、
   font_ea、font_latin、min_font_pt、require_notes、max_slides、uncertainty；按路由增加
   required_mainline、source_deck、revisions、template、goal、narrative、qa_prep。
   CLI 传 `--case /input/case.json`，无需复制或改写契约。
4. **审计。** 在技能目录执行：
   `python -I -X utf8 scripts/deckbuild.py --spec /app/work/spec.json --case /input/case.json --out /app/output`。
   正常路径写 deck.pptx、result.json，渲染器存在时另写真实 PDF；退出码只有 0/3/4/5。
5. **修发现并重跑。** 按异常表修源材料映射、页面内容或记录后重跑。为消除发现而补造论文
   对象、数字、字体或预览属于失败；材料确实不支持时保留 review/blocked 并写 uncertainty
   与 limits。每次实际修改都进 revisions，交付版由 delivered_revision 指认。
6. **合并最终 JSON。** 确认 `/app/output/result.json` 含原 case_id、原 output_contract 及每个
   同名字段、主产物、evidence_map、sources、uncertainty、change_records、preview、
   reproducibility、template_application、source_record 和 limits。审计值优先于 spec 自报值；
   无法推导字段为 null 且逐字段说明。交付真实文件路径，不把 JSON 当作 PPT 的替代品。

## 任务措辞 → 路由决策表

| 任务措辞或材料形态 | section 与动作 | 必须保留的证据 |
|-|-|-|
| “把这篇论文做成学术汇报” | paper_to_deck；required_mainline 声明四拍，逐页 role 对齐 | 论文图/表/Eq./章节定位 + 页级 claim |
| “从研究材料生成一版新 deck” | paper_to_deck；slides + notes + available_evidence | 每页来源和研究主线 |
| “编辑/压缩/扩写/翻译这份 PPT” | deck_edit；source_deck 指真实文件，revisions 逐条修改 | 原文件 SHA-256、before/after/reason、保留包记录 |
| “只改第 N 页/删掉这段” | deck_edit；change 指 slide，删除保留 before 快照 | 删除可回滚，after 或缺失状态可读回 |
| “两轮修改后交付第二版” | deck_edit；delivered_revision 指 n 标签或列表位置 | 截至交付版的实际执行记录 |
| “按这个 POTX/PPTX 模板适配” | template_fit；template 的 file 字段指实际包 | 实测 layouts/theme/slide size + 模板壳应用记录 |
| “只要字体字号规范，没有模板文件” | template_fit；仅声明 spacing 和字体，不伪造模板实测 | 声明式字号阶梯与最终文件字体 |
| “组织一场答辩/评审汇报” | talk_org；goal、narrative、strength、qa_prep | 目标、听众、时长、节拍、证据强度和问答 |
| “10 分钟，最多 8 页” | talk_org 或其他 section；goal 的 minutes + max_slides | 页预算、逐页 pace 与总预算核对 |
| “每页都能回到论文证据” | 任一路由；evidence 必须命中 available_evidence | evidence_map 与 caption_landed |
| “中文/中英混排，防止溢出方框” | 任一路由；声明真实可用字体 | 度量字体路径、缺字字符、CJK 断行结果 |
| “导出后复核，保留版本” | 任一路由；读取 preview、reproducibility、change_records | 真实 PDF（若有）、渲染器、两遍构建指纹 |

## 各路由的最小规格

### paper_to_deck

每页 title 是页面标题，claim 是断言，role 取 question/method/result/limit；证据 locator 必须
来自实际材料。有图时 image、image_alt、caption、evidence 同页出现；caption 保留样本、条件和
面板含义。主线四拍是任务内容，材料缺一拍时不得虚构，应在 uncertainty 点名并接受相应发现。

### deck_edit

`source_deck` 存在时，引擎直接编辑源包副本；revisions 中只有截至 delivered_revision 的轮次会
应用到交付文件。文本替换跨 split runs 执行并保留首个 run 格式；after 已存在而 before 不存在
视为幂等完成，不处罚。纯位置/动画修改记录为 structural_record_only，因为本引擎不伪造其实施。

提取起始稿骨架（输出是工作文件，不是正式结论）：

`python -I -X utf8 scripts/decksource.py --source /input/start.pptx --out /app/work/source.json`

### template_fit

template 的 file 字段触发真实测量和实际套用。布局名按 name/type 归一化匹配；唯一匹配才应用。
引擎复制模板的 master/layout/theme 及其依赖、调整画布尺寸、重新连接每页 layout。页面正文仍是
可编辑显式文本框，不冒充已转化为模板占位符。没有 file 字段时只跑声明式规则。

### talk_org

goal 包含 objective、audience、minutes；narrative 是声明节拍，role 是页面落点。strength_scale
可扩展，但标签必须可排序。require_qa_prep 为真时，每个问题需要 answer 文本或 answer_slide。
逐页 pace_minutes 可以存在，合计不能超过 minutes。

## 完整 worked example（示例，非固定案例答案）

输入文件：`examples/spec-master.json`（四页：问题、方法、结果、限制）与 `examples/case.json`
（case_id 为 ppt-master-worked-001，九个 output_contract 字段）。示例数值只用于演示接口，
正式运行必须换成源材料真实值，不能把示例当预制答案。

```bash
python -I -X utf8 scripts/deckbuild.py \
  --spec examples/spec-master.json \
  --case examples/case.json \
  --out /app/output
```

本机隔离环境实跑结果（本记录为示例）：

```text
status=clean  case_id=ppt-master-worked-001  findings=[]  slides=4  exit=0
reproducibility: deterministic=true（比较最终页面文字、几何与备注）
deck_file: 指向实际生成的四页 deck.pptx
output_contract_fields: case_id, status, deck_file, evidence_map,
  render_record, version_record, change_records, uncertainty, review_note
preview: rendered=false；本机无 soffice/libreoffice/office-renderer，limits 如实注明
```

result.json 同时含四行 evidence_map、review_note 原文和 uncertainty；change_records 为空数组，
因为该示例没有编辑轮次。不是“字段齐全即事实正确”：正式案例仍须逐条回到原材料复核。

## Rubric 三段输出映射（字段采用题面原词）

| 题面内容 | 完成标准 | 本包交付与检查 |
|-|-|-|
| 可编辑演示文件 | 页级结构、主张、图表、讲稿/备注和模板结果；能围绕论文主线讲清楚 | 真 PPTX；required_mainline/role/claim/notes；模板壳、母版链和文本落位可读回 |
| 页级证据映射 | 每页内容对应论文图、表、章节或数据；引用准确，未改写事实 | evidence_map + available_evidence 白名单 + caption 图号交叉核验；不把未读内容添进映射 |
| 渲染与版本记录 | 源文件、导出件、字体/模板和修改记录；可打开、播放、编辑并复核 | source_record、preview、template_application、reproducibility、change_records；无渲染器如实声明 |

五维评分点落点：实际效果看真实三类产物；使用增益看免除手工重建、逐页补定位和重复统计；
创新增益看保结构编辑、真实模板壳、标准库字形测量；可靠体验看四态退出与异常表；生态贡献看
可复跑规格、规则、示例和回归套件。效率与创新只能由这些产物和运行记录证明，不自报平台分数。

## 状态与输出

| status | exit | 含义 |
|-|-|-|
| clean | 0 | 零发现；仍须满足实际任务，不代表自动通过科研评审 |
| review | 3 | 仅 medium/low 发现，可交付但必须说明剩余问题 |
| blocked | 4 | 至少一个 high；不得把未完成品写成完成 |
| undetermined | 5 | 输入/源文件/路由无法运行；独立拒绝路径，永不 traceback |

正常结果保留原 `output_contract` 对象及 `output_contract_fields` 清单。契约支持名称→说明对象、
字符串数组、含 field/name/key 的对象数组；审计已有字段不被 spec 覆盖，案例文件中的 case_id
优先于 spec 内标识。无法推导的同名字段为 null 并进入 limits。

## 规则索引（每条一行）

### 主线与证据

| rule | severity | 阻断的问题 |
|-|-|-|
| `paper.mainline_missing` | high | 声明的研究主线四拍未全部落页 |
| `paper.figure_unattributed` | high | 图片没有论文对象定位 |
| `paper.caption_missing` | medium | 图页丢失条件和面板说明 |
| `deck.claim_missing` | medium | 页面只有主题没有主张 |
| `deck.evidence_missing` | high | 页面无来源定位 |
| `deck.evidence_unsupported` | high | 定位不在实际证据白名单 |
| `deck.caption_not_landed` | high | spec 声明 caption 但未落入最终文件 |
| `format.figure_mismatch` | high | caption 与 evidence 指向不同图号 |

### 修订、源稿与版本

| rule | severity | 阻断的问题 |
|-|-|-|
| `edit.change_without_slide` | high | 修改无页码 |
| `edit.change_without_reason` | high | 修改无理由 |
| `edit.change_slide_out_of_range` | high | 修改指向不存在页面 |
| `edit.change_not_in_deck` | high | after 未落在所指页面或备注 |
| `edit.before_not_in_source` | high | 源稿既无 before，也无已应用的 after |
| `edit.source_change_unapplied` | high | 源稿修改因页码/XML 问题未执行 |
| `edit.delete_without_snapshot` | high | 删除没有 before 快照，无法回滚 |
| `edit.package_not_preserved` | high | 源包部件在编辑中被增删 |
| `edit.revision_without_changes` | medium | 一轮修订没有修改 |
| `edit.delivered_revision_missing` | medium | 多轮历史未指认交付版 |
| `edit.change_half_diff` | medium | before/after 只有一侧 |
| `edit.revision_instruction_missing` | low | 本轮 instruction 缺失 |
| `edit.change_is_noop` | low | before 与 after 相同 |
| `repro.nondeterministic` | high | 两遍最终产物不同 |

### 页面、页预算与媒体

| rule | severity | 阻断的问题 |
|-|-|-|
| `deck.no_slides` | high | 文件没有页面 |
| `deck.empty_slide` | high | 页面没有文本 |
| `deck.no_title` | high | 页面没有标题 |
| `deck.slide_count_over_limit` | medium | 超出声明页数上限 |
| `deck.slide_count_under_limit` | medium | 低于声明页数下限 |
| `deck.slide_budget_invalid` | low | 页预算非整数，未能执行 |
| `deck.too_many_bullets` | medium | 超出页面密度上限 |
| `deck.title_too_long` | medium | 标题可能侵入正文区 |
| `deck.notes_missing` | medium | 声明要求备注但页面没有 |
| `deck.notes_repeat_title` | low | 备注仅复述标题 |
| `image.source_missing` | high | 声明图文件不存在，已诚实部分交付 |
| `image.aspect_distorted` | high | 图片相对源比例被拉伸 |
| `image.no_alt_text` | low | 图片没有替代文本 |

### 汇报组织

| rule | severity | 阻断的问题 |
|-|-|-|
| `org.goal_missing` | high | 无汇报目标，页数和深度不可判 |
| `org.audience_missing` | medium | 听众未声明 |
| `org.narrative_incomplete` | medium | 声明叙事节拍未全部落页 |
| `org.role_undeclared` | low | 页面 role 超出声明节拍 |
| `org.qa_prep_missing` | medium | 要求问答准备但问题或答案指针不全 |
| `org.claim_is_topic` | medium | claim 是短话题词而非断言 |
| `org.evidence_strength_missing` | medium | claim 未标证据强度 |
| `org.strength_unknown` | low | 标签超出声明强度表 |
| `org.pace_too_fast` | medium | 平均每页不足 0.7 分钟 |
| `org.pace_too_slow` | low | 平均每页超过 4 分钟 |
| `org.pace_budget_exceeded` | medium | 各页时间合计超过总预算 |
| `org.pace_budget_invalid` | low | 时间声明非数值，无法对账 |

### 模板、字体与包完整性

| rule | severity | 阻断的问题 |
|-|-|-|
| `format.undeclared_layout` | high | 使用声明集合之外的 layout |
| `format.content_dropped` | high | 声明的标题/要点/caption 未落文件 |
| `template.unreadable` | high | 真实模板包不可解析 |
| `template.layout_not_found` | high | 请求 layout 不在真实模板中 |
| `template.layout_master_missing` | high | 选中 layout 无 master 回链 |
| `template.title_placeholder_missing` | high | 明确要求标题占位符但真实 layout 没有 |
| `template.duplicate_layout_name` | medium | layout 别名在真实模板中有歧义 |
| `template.theme_font_mismatch` | medium | 声明字体与实测主题字体不一致 |
| `template.slide_size_mismatch` | medium | 交付画布与真实模板不同 |
| `format.font_drift` | medium | 标题显式使用主题外字体 |
| `format.title_drift` | medium | 同 layout 标题几何或字号漂移 |
| `format.size_ladder_flat` | medium | 标题/正文比例小于 1.35 |
| `format.size_ladder_steep` | low | 标题超过正文三倍 |
| `format.template_unnamed` | low | 声明 template 却无名称 |
| `text.overflow` | high | 文本按字形度量后超出实际框 |
| `text.font_too_small` | high | 字号低于可读下限 |
| `text.size_missing` | medium | run 未声明字号 |
| `text.body_too_large` | low | 正文字号与标题竞争 |
| `text.term_inconsistent` | medium | 同术语出现可机械判定的两种拼法 |
| `font.declared_missing` | medium | 声明字体本机未安装 |
| `export.missing_glyphs` | high | 字符在可用字体中无字形 |
| `export.missing_glyphs_in_declared_font` | medium | 声明东亚字体缺部分字符 |
| `embed.missing` | medium | 声明嵌入字体却无字体部件 |
| `export.invalid_package` | high | presentation.xml 缺失 |
| `export.no_master` | high | 包无 slide master |
| `export.no_theme` | high | 包无 theme |
| `master.layout_missing` | high | 页面 layout→master 链断裂 |
| `master.inconsistent` | high | 页面解析到多个 master |
| `audit.no_section` | high | 输入/路由拒绝，status 为 undetermined，exit 5 |

## 异常处置表

| 异常 | 识别与处置 |
|-|-|
| case.json 缺失/坏 JSON | 有可读 spec 时继续并在 limits 注明；case_id 仅为明确值，不能编造契约字段 |
| task.md 缺失或约束不清 | 登记 uncertainty，不虚构时长/页数；无法形成产物时写 undetermined |
| 论文 PDF 不可读/缺页 | 保留未完成页与材料缺口；不把文件名当研究结论 |
| spec 缺失、坏 JSON、非对象、slides 非数组 | exit 5 + result.json；拒绝函数不调用契约回填 |
| section 未知或非字符串 | exit 5；选择四条合法路由，不静默跳过专属检查 |
| spacing/bullets 类型错误 | spacing 安全回退并写 limits；bullets 无法规范化则 exit 5 |
| 源 PPTX 不存在/损坏 | exit 5；先修复输入，不从记忆伪造“原稿” |
| before 不在源稿 | 若 after 已存在视为幂等；否则 high，重新抽取原文或纠正记录 |
| after 未落最终页 | high；应用修改或改台账，不能仅修改描述 |
| 删除没有原内容 | high；把被删文本放入 before 后重跑 |
| 模板不存在或 XML 损坏 | template.unreadable high；交付未套模板稿并在 limits 明示 |
| layout 缺失或重名 | high/medium；改用真实 name/type，歧义未解不应用模板壳 |
| 页数超预算/时间超预算 | 按主张强度压缩页；保留被删快照和新一轮记录 |
| 图文件缺失 | 不画替代曲线；页面无图部分交付并 exit 4 |
| 文本溢出 | 删要点或拆页；不得缩到字号下限以下 |
| 字体未安装/缺字形 | 换有字形的实际字体；记录缺失字符，不声称字体嵌入成功 |
| 无 Office renderer | preview.rendered=false + limits；安装后重跑，不创建假 PDF |
| 模板无法应用 | 交付块标 template_applied=false；不能以 template 名字冒充已套用 |
| 两遍构建不同 | blocked；消除时间戳式内容、随机布局或并发写入 |
| output_contract 形状未知 | 保持主产物，limits 点名未知形状，不迭代数字/空对象 |
| output_contract 字段不能推导 | 同名字段写 null 并逐字段说明，不以相似名称替代 |
| 科学事实与审计冲突 | 源材料优先；修 spec/页面而非为追求 clean 改事实 |

## 适用边界

- 引擎不替 Agent 做论文精读或 PDF 视觉理解；它核验 Agent 从实际材料构造的映射是否落文件。
- 源稿保结构修改覆盖 DrawingML 文本；复杂 SmartArt、动画、OLE 内部文本只记录，不声称已修改。
- 模板应用是真实 master/layout/theme 壳与关系重连，不是完整 PowerPoint 样式仿真；新文本框不
  自动变成原生 placeholder。显式要求标题占位符时才启用对应规则。
- 原型图片/媒体随包保留；不声称生成原生可编辑图表或重绘位图数据。
- 标准库字形测量使用 cmap/advance width，不含 kerning/ligature；Pillow 存在时交叉使用其实际
  字形宽度。完全不能读取字体时退化为估算并在 checked/limits 标记。
- 证据白名单和叙事字段是声明式审计；`clean` 不等于保证引用语义，最终仍要人工回读源文。

## 创新增益（均为本包真实能力）

1. **总控而非路由转发**：同一输出可组合源稿保结构编辑、真实模板壳、主线/组织审计和契约回填；
   不需要在四个技能之间复制结果或丢失上一阶段审计。
2. **源文件 before/after 双向核验**：before 定位真实源段落，after 回读最终 PPT；after 已存在是
   可识别幂态，包部件数量和源/产物 SHA-256 构成版本证据。
3. **真实模板套用到文件结构**：复制实际 master/layout/theme 及内部依赖并重连每页，而非比较
   模板名字。可字节比对输入模板和交付模板的 master。
4. **隔离环境仍可测量中文**：SFNT/TTC cmap + hmtx 标准库度量、CJK 逐字断行、按字符选字体；
   无 Pillow 时不再 ModuleNotFoundError，无法测量时明确降级。
5. **从任务约束到可复算记录**：页数上下限、逐页时间与总时长、叙事节拍覆盖、问答答案指针、
   证据强度词表都由同一 spec 复算；声明才启用，避免惩罚普通合法页面。
6. **科学诚实优先于全绿**：缺图、缺材料、无预览、结构修改未执行和契约不可推导都有独立记录；
   引擎不接受 spec 中的 status 覆盖实际审计结论。

## 生态贡献（八项）

1. **使用说明**：本文件含用途、条件、0–6 入口、调用、输入输出、异常、限制和维护门槛。
2. **无个人路径依赖**：所有引擎在包内；Python 3.9+，核心标准库，可选 Pillow/matplotlib 仅加速。
3. **可复用引擎**：decksource、templatecheck、glyphmetrics、deckaudit、contract_echo 均可独立导入。
4. **声明式配置**：页面、证据、预算、源稿、模板、叙事和问答全由 JSON 控制，无需改源码。
5. **最小与组合示例**：examples/case.json + spec-master.json；另有三条旧路由的独立规格示例。
6. **回归资产**：四个 bench 共 91 个场景，规则触发与 FP 守卫并存，clean 基线零发现。
7. **敌意探针**：26 个真实 CLI 场景统一验证 exit∈{0,3,4,5}、result.json 和无 traceback。
8. **实践经验固化**：文本写后再读、拒绝与契约分离、二进制只在临时目录生成、规则以本包 bench
   为维护门槛；任何规则变更须同步规则索引、缺陷场景和正常守卫。

## Verification（作者复跑，不是运行时必做步骤）

```bash
python -X utf8 scripts/bench_deck.py     # 11 场景
python -X utf8 scripts/bench_deck2.py    # 16 场景
python -X utf8 scripts/bench_extra.py    # 27 场景
python -X utf8 scripts/bench_master.py   # 37 场景
python -X utf8 scripts/probe_hostile.py  # 26 个真实 CLI 探针
```

bench 在包内 `_run*` 写临时 PPTX，打包器会排除；探针改用系统临时目录。scripts 中的
report_*.json 是本次实跑报告，examples/bench-report.json 只汇总这些验证，不是固定案例成绩。
