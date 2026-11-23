---
name: db-sqlite-analysis
description: >
  科研数据库查询与分析：在授权的本地 SQLite 快照上真正执行一个只读 SELECT/WITH，交付
  schema、SQL、真实 EXPLAIN QUERY PLAN、结果行、字段字典解释、跨表连接键、聚合粒度、
  NULL/重复/混合类型/单位处理、行数与独立金标准校验、执行日志和快照哈希，而非只生成
  一段“像 SQL 的文本”。原生 authorizer 拒绝写入、ATTACH、PRAGMA、多语句与危险文件/
  扩展函数，保持原始行不改写，单位换算另写新列并留因子。用于科研 SQLite 库表发现、
  查询执行、结果抽取、跨表统计与复核。无 SQLite 文件/执行环境或遇非 SQLite 驱动时明确
  undetermined；不伪装 PostgreSQL/MySQL/网络连接成功，不自动猜造科学结论。
---

# db-sqlite-analysis（科研数据库查询与分析）

本 Skill 的主线是 **schema → 只读 SQL → 真实计划/执行 → 结果质量与独立校验 → 可追溯结论**。
问题到 SQL 的语义选择由 Agent 根据 task、数据字典和实际 schema 完成；引擎负责执行与安全/
结果验证，不自称拥有自然语言查询规划器，也不把运行结果填回 expected_rows 伪装独立验证。

## 运行时工作流（以交付结束）

平台输入为 `/input/case.json`、`task.md` 和授权数据材料。先读取数据字典、字段语义、时间范围、
目标粒度和只读权限。所有分析工作文件放 `/app/work`，最终结构化结果和快照证据放 `/app/output`。

| 步 | 动作 | 证据 |
|-|-|-|
| 0 读案例 | 原样记录 `case_id` 和原始 `output_contract` 全字段；明确问题要求的表、字段、筛选、时间区间和跨表维度 | 契约与任务清单 |
| 1 定位快照 | 找到真实 `.sqlite/.db` 文件；非 SQLite 或缺执行环境时写 undetermined，不能假装连上 | 文件路径与驱动判断 |
| 2 形成查询 | 依据实际库表与数据字典选择 SELECT/WITH、JOIN 键、GROUP BY、ORDER BY 和参数；指定结果 `grain` | 可解释的 spec.json |
| 3 先跑一遍 | 调用下方 CLI；引擎同时发现 schema、执行计划并取回真实行 | SQL、schema、plan、rows、result 初版 |
| 4 独立核对 | 对照行数/列、NULL、重复粒度、单位和独立复算；修正查询后重跑，不用返回值充当金标准 | expected_* / independent_check 结果 |
| 5 分析结论 | 只写与 SQL 行、质量检查和独立校验一致的结论；未覆盖与不确定性如实保留 | conclusions + field_interpretation |
| 6 最终交付 | 检查 `case_id`、原契约每键、查询与计划、行列数、日志和 artifacts；blocked/refused 不谎称 clean | `/app/output/result.json` 与完整审计包 |

作者自查命令不是正式案例的强制前置步骤。平台案例缺材料、缺字段、权限不足或查询失败要分别
记录，不能静默换库、换表或补造结果。

## 最小真实调用

本包 `examples/make_example.py` 会即时创建一个**非官方**小型 SQLite 快照，不把二进制数据库
塞进 Skill。假设安装前缀为 `/skills/weekly-skill`：

```bash
python /skills/weekly-skill/examples/make_example.py --out /app/work/db-example
python -X utf8 /skills/weekly-skill/scripts/dbquery.py \
  --db /app/work/db-example/example.sqlite \
  --spec /skills/weekly-skill/examples/spec.json \
  --out /app/output
```

这个示例实际聚合 2 个实验组、4 条测量，独立字面金标准为 Control `n=2, mean=2.0`、Treated
`n=2, mean=3.5`；运行成功为 exit 0。`examples/example-result.json` 是该真实运行的路径规格化
副本，带 `example_note`，不是官方案例答案。

也可让引擎同时读取案例契约并覆盖 SQL：

```bash
python -X utf8 /skills/weekly-skill/scripts/dbquery.py \
  --db /input/authorised.sqlite \
  --case /input/case.json \
  --spec /app/work/query-spec.json \
  --sql "SELECT id, name FROM experiments ORDER BY id" \
  --task /input/task.md \
  --out /app/output
```

`--case` 只把案例中 spec 尚未定义的值并入，包括 `case_id`、`output_contract`；命令行 `--sql`
最后覆盖。`--db` 优先于 spec 的 `db_path`、`database`。跨区域连接字符串和非 SQLite driver 不会
被当成 SQLite 文件尝试。

## spec：查询、语义与校验必须同时落地

```json
{
  "case_id": "demo-db-001",
  "output_contract": ["status", "rows", "query_plan", "execution", "quality_report", "conclusions", "limits"],
  "driver": "sqlite",
  "sql": "SELECT e.name AS name, COUNT(m.id) AS n, AVG(m.value) AS mean_value FROM experiments e JOIN measurements m ON e.id = m.experiment_id GROUP BY e.name ORDER BY e.name",
  "parameters": [],
  "grain": ["name"],
  "data_dictionary": {
    "experiments.name": {"description": "experimental arm", "semantic": "categorical"},
    "measurements.value": {"description": "response", "unit": "AU", "semantic": "numeric"},
    "n": {"description": "measurement count", "semantic": "count"},
    "mean_value": {"description": "mean response", "unit": "AU", "semantic": "numeric"}
  },
  "allowed_joins": [{"left": "experiments.id", "right": "measurements.experiment_id"}],
  "not_null": ["name", "n"],
  "expected_row_count": 2,
  "expected_columns": ["name", "n", "mean_value"],
  "expected_summary": {"row_count": 2, "sums": {"n": 4}},
  "independent_check": "SELECT CASE WHEN (SELECT COUNT(*) FROM measurements)=4 THEN 1 ELSE 0 END",
  "numeric_tolerance": 1e-9,
  "max_rows": 10000,
  "timeout_seconds": 20
}
```

### 字段语义与约束如何执行

| 字段 | 真实机制 |
|-|-|
| `sql` / `query` | 一条 SELECT 或 WITH...SELECT；`parameters` 为数组或对象，不用字符串插值代替参数化 |
| `data_dictionary` | 支持 `{field: meta}`、`{table.field: meta}` 或带 name/table 的列表；结果字段回链描述、单位、semantic；多重限定名匹配报歧义 |
| `grain` | 声明结果行应唯一的键；实际重复组及行号报 `validation.grain_not_unique`。GROUP BY 的字段可保守推断，复杂表达式仍应显式声明 |
| `allowed_joins` | 没有外键但语义确认的 `{left,right}` 连接对；未登记连接给提示而非硬猜外键 |
| `not_null` | 结果列 NULL 直接报 high，不改成 0、空字符串或“正常” |
| `expected_row_count`、`expected_columns`、`expected_rows` | 与真实输出比对。`expected_rows` 必须来自独立金标准/另一实现，不能复制本查询输出 |
| `expected_summary` | 对 `row_count`、`sums`、`means`、`mins`、`maxs`、`nulls`、`distinct` 从实际分析行重新计算比对 |
| `numeric_tolerance` | 数值期望的相对容差，默认 1e-9；结构和文本仍精确比较 |
| `independent_check` | 另一条只读 SQL，必须返回一行一列的期望标量（默认 1）；SQL 与计划同样留存 |
| `max_rows`, `timeout_seconds` | 分别为 1..100000（默认 10000）与 0.1..60 秒（默认 20）；超行只多取一行截断证据并 blocked |
| `snapshot_copy`, `snapshot_max_bytes` | 默认对不超过 5MB 的授权文件保留字节快照；更大文件只保留哈希并写限制 |
| `interpretation` | 可选的科研解释；`conclusions.trace` 把解释绑定到 query/rows sha256，缺省只交付执行事实 |

## 只读安全是原生执行约束，不是关键词过滤

1. SQL 扫描器忽略字符串/注释中的分号，只接受一条 SELECT/WITH；写操作为第一关键字直接拒绝。
2. `file:///...?...mode=ro` 打开本地快照，并设置 `PRAGMA query_only=ON`。
3. SQLite `set_authorizer` 只允许 SELECT、READ、FUNCTION、RECURSIVE；其余动作默认 DENY。
   因此 WITH 后隐藏 DELETE、INSERT/UPDATE/DDL、ATTACH、PRAGMA 都不能借首关键字绕过。
4. `load_extension`、`readfile`、`writefile`、`fts3_tokenizer`、`zipfile` 等危险文件或扩展函数双重拦截，
   不读取数据库外文件。扩展加载被禁用，ATTACH 数限制为 0（运行时支持时）。
5. `EXPLAIN QUERY PLAN` 与正式执行使用同一 authorizer。求值超时由 progress handler 中断。
6. 执行前后对数据库做 sha256，字节变化报 `connection.snapshot_changed`。

SQLite 官方[authorizer 实现](https://github.com/sqlite/sqlite/blob/master/src/auth.c)说明 READ 回调携带表/列，DENY 使语句
不会执行；本包把该原生能力用于实际安全边界，并保存真实 READ 表列证据。不是只依靠 SQLGlot
或自己写一个正则就宣布安全。

## schema、join、聚合与结果质量

### schema 卡片

直接读 `sqlite_master`、`table_info`、`foreign_key_list`、`index_list`、`index_info`，附表行数、
视图定义、主键、索引、隐式单列主键引用，以及 `user_version`、`schema_version`、`application_id`、`journal_mode`。
schema 不可读时通常是损坏/非 SQLite 文件，返回 undetermined，不编造表结构。

### 跨表关联

`relationships` 同时保存原生 READ 表列、JOIN ON/USING 的保守提取、外键/显式 allowed_joins 支持。
多个表被显式 JOIN 但没有可识别的关联条件时是 high。非外键连接不自动判错，给
`join.key_not_declared` 提醒人工按字典确认。逗号连接在 WHERE 中有条件时不会被误报为无条件 join。
复杂嵌套、引用带引号的表名或函数表达式时，文本提取可能不完整，必须结合 query_plan 和显式 grain；
不能把启发式结果当完整 SQL AST 证明。

### 聚合、NULL、重复与单位

- GROUP BY 的简单结果字段（含带表名限定的列对应输出名和位置序号）用于推断 grain；实际重复组
  会被点名。声明 `grain` 是控制一对多膨胀的首选方式。
- 每列报告 `null_count`、`non_null`、`missing_fraction`、`distinct_count`、`storage_types`、`mixed_storage_types`。
  SQLite 原始行保留在 `rows`，规范化分析行另存 `analysis_rows`。
- 完全重复结果行保留并提示；`grain` 重复是更严格的粒度错误。SELECT * 的重复输出列名以
  `__2` 等后缀保留，绝不因转 dict 覆盖一列，同时给 finding 和 `column_name_map`。
- `units` 按 `{column: {source_unit/unit 或 unit_column, target_unit, new_column?}}` 配置。
  只转换数值，不解析“1 mg”等文本；未知/跨量纲单位或缺单位进 finding，目标值写 null。
  原始值不改写，`unit_changes` 记录行列、源/目标单位、量纲、因子与 offset。
- 已实现质量、体积、长度、时间、物质的量/摩尔浓度、能量、温度、比例单位；大小写有语义：
  m=metre、M=molar、mM=millimolar、mm=millimetre。摄氏/华氏/Kelvin 使用显式偏移。
  未列出的 domain-specific 单位应留在原列并说明，不能随意近似。

单位示例：

```json
"units": {
  "concentration": {"unit_column": "concentration_unit", "target_unit": "mM"}
}
```

原始 `1000 uM` 在 `analysis_rows` 的 `concentration__mM` 为 `1.0`，`rows` 的 `concentration` 仍为 `1000.0`。

## 输出契约与实际产物

`result.json` 包含：

| 字段 | 内容 |
|-|-|
| `case_id` | 原样案例 ID；失败结果同样尽力回填可读 case/spec |
| `analysis_result.rows` / `rows` | SQLite 原始结果行对象，NULL 保留；BLOB/非有限数用结构化标记，不伪造文本 |
| `analysis_result.analysis_rows` / `analysis_rows` | 经显式单位规范化的独立行；无转换时等于原行 |
| `analysis_result.summary`, `quality_report` | 实际复算汇总与每列质量 |
| `schema`, `field_interpretation` | 原生库表卡片和数据字典映射，歧义不静默选择 |
| `query`, `query_plan`, `relationships`, `aggregation` | 原 SQL/参数、真实计划、关联键、GROUP BY 与 grain 校验 |
| `execution` | 只读事实、SQLite 版本、实际行列数、truncated、表列 READ、执行前后哈希、rows/query sha256 |
| `conclusions` | 行列执行事实、grain/independent check、可选 interpretation 及证据哈希 |
| `unit_changes` | 每个单位换算的原始值、目标值、因子、offset、量纲和行列 |
| `artifacts`, `provenance` | 文件、数据库快照与版本/哈希；task 提供时另记 task sha256 |
| `findings`, `severity_counts`, `limits` | 异常、级别、未覆盖语义与不可推导内容 |
| 原始 `output_contract` 其他键 | 引擎已有字段优先；spec 给定值直通；不可推导致 null + 逐项 limits |

成功执行会写出：`query.sql`、`schema.json`、`query_plan.json`、`rows.json/csv`、
`analysis_rows.json/csv`、`execution_log.json`、`result.json`，以及符合大小阈值的
`database_snapshot.sqlite`。失败查询的 SQL 和结构化失败同样保留；失败路径不声称已执行或行数正确。

### 状态与退出码

| status | exit | 含义 |
|-|-|-| 
| clean | 0 | 查询与所有显式约束通过，无 finding |
| review | 3 | 空结果、重复行/列、混合类型、数据字典缺失等非 high 情况 |
| blocked | 4 | 返回结果与期望不符、粒度重复、非预期 NULL、缺 join 条件、单位不可换算或结果截断 |
| refused | 5 | 非只读/多语句/危险函数、SQL 或参数被 SQLite 拒绝；没有成功查询结果 |
| undetermined | 5 | 缺数据库/无效 SQLite/非 SQLite driver、输入不可读、超时或运行能力不可确定 |

可预见的错误均写 `result.json` 和 finding，不以 traceback 收场；CLI 缺少 `--out` 等调用用法
错误由 argparse 返回 2。不能把 refused/undetermined 的 `execution.status=not_completed` 当成 0 行。

## 限制与失败处置

- 只执行本地 SQLite 文件，不提供 PostgreSQL/MySQL/云数仓/网络驱动。其他 driver 明确 undetermined。
- Agent 必须依据 task 和数据字典写 SQL；引擎不会从问题猜表名、连接路径或统计口径，也不会
  无条件自动修复 SQL。`query.sql_error` 给出 SQLite 定位，Agent 修后重跑。
- JOIN 文本分析是保守辅助，不是完整 SQL AST。复杂查询配合显式 `allowed_joins/grain/expected_*`；
  真正的安全由原生 authorizer 保证，真正的正确性由独立复算保证。
- 不自动从重复实验判断技术/生物重复，不擅自去重、平均或把 NULL 当 0。
- 行数截断时不允许作全表聚合结论；提高资源上限或在 SQL 内完成正确聚合。
- WAL 活跃写入的源数据库不是稳定快照；执行前后哈希只能发现字节变化，不能冻结外部写入。
- expected_rows/summary/independent_check 只证明其声明的验证路径；若声明本身错误，引擎不能证明
  金标准正确。科学因果解释不因 SQL 成功而成立。

| 症状 | 规则与退出 | 处理 |
|-|-|-|
| 空结果 | `query.empty_result`, review 3 | 检查筛选和时间范围，不补造行 |
| 缺库/损坏库/非 SQLite | connection.* 或 driver 规则，undetermined 5 | 提供授权 SQLite 快照或换正确执行环境 |
| SQL 语法、字段或参数错误 | `query.sql_error`, refused 5 | 按 SQLite 错误修 SQL/字段/参数再跑 |
| 写操作/ATTACH/PRAGMA/多语句/文件函数 | query.not_read_only / multiple_statements / security.*, refused 5 | 只提交授权 SELECT/WITH，不能关闭安全检查 |
| 结果为空或重复粒度 | empty_result 或 grain_not_unique | 核对筛选、join 键、聚合粒度；不要直接平均 |
| 单位不明/不兼容 | source_missing / incompatible / mixed_units | 回查字典，声明同量纲 target 或保留原单位 |
| 独立复算失败 | validation.* / independent_check_failed, blocked 4 | 同时复核 SQL 与金标准，绝不只改报告数 |
| 数据字典缺失/歧义 | schema.data_dictionary_missing / field_ambiguous | 明确字段语义，不能根据列名猜单位 |

## 完整 finding 规则索引

- Connection：`connection.unavailable`、`connection.failed`、`connection.invalid_database`、
  `connection.unsupported_driver`、`connection.snapshot_changed`、`runtime.failed`。
- Input：`input.spec_unreadable`、`input.spec_not_object`、`input.spec_invalid`。
- Query：`query.sql_missing`、`query.too_large`、`query.unterminated_quote`、`query.multiple_statements`、
  `query.not_read_only`、`query.parameters_invalid`、`query.sql_error`、`query.timeout`、
  `query.empty_result`、`query.rows_truncated`、`query.duplicate_column_names`、`query.unnamed_column`。
- Schema/join：`schema.data_dictionary_missing`、`schema.field_ambiguous`、
  `join.condition_missing`、`join.key_not_declared`。
- Data：`data.duplicate_rows`、`data.mixed_storage_types`。
- Validation：`validation.row_count_mismatch`、`validation.columns_mismatch`、`validation.rows_mismatch`、
  `validation.summary_mismatch`、`validation.independent_check_failed`、`validation.grain_missing`、
  `validation.grain_not_unique`、`validation.not_null_column_missing`、`validation.unexpected_null`。
- Units：`unit.spec_invalid`、`unit.source_missing`、`unit.non_numeric`、`unit.incompatible`、`unit.mixed_units`。
- Security：`security.read_only_violation`。

## Requirements

Python 3.10+，仅标准库（重点为 `sqlite3`）。无第三方包、无网络、无系统 sqlite3 CLI 依赖。
Python 必须使用支持 `mode=ro` URI、authorizer、query_only 的 SQLite 构建；若平台不提供 SQLite
或文件不可执行，则明确 undetermined。模块兼容没有 `sqlite3.version` 的新 Python，以真实
`sqlite3.sqlite_version` 记录运行时版本。

## Verification（作者自查，非运行时前置）

```bash
python /skills/weekly-skill/scripts/bench_dbquery.py
```

当前 32/32 场景通过。每次运行都在系统临时目录生成已知小库；涵盖真实 SELECT/JOIN/GROUP BY、
独立聚合金标准、NULL/not_null、重复粒度、单位与温度换算、查询计划、只读攻击、多语句、
CTE 写、危险函数、重复输出列、截断、失败 SQL 留证、缺库/坏库/非 SQLite、契约直通和结果字节
确定性。测试不会留下或提交二进制数据库。
