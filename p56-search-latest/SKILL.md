---
name: search-latest
description: >
  最新文献发现与追踪。用于 retained snapshots 的订阅配置—显式时间窗—增量去重—版本/状态更新—
  提醒状态—next_state 闭环；区分 online/issued/created/deposited/indexed/imported_at，
  处理跨时区半开窗口、延迟入库、已读/追踪抑制和幂等重放。绝不伪造当前时间、实时检索或已发送提醒。
---

# search-latest（最新文献发现与追踪）

主引擎为 latest-literature-tracker/v2；旧 file-search/v1 日期字符串探针仅保留兼容，不等价于增量追踪。

## 核心闭环

`previous_state + retained sources + [start,end) → 日期解释 → 身份归并 → 分类 → prepared reminders → 条件提交 next_state`

| rubric | 实际行为 |
|-|-|
| 时间窗 | 必须显式 start/end；`[start,end)`，统一换算 UTC。offset-aware 值保留 raw 并输出 UTC；naive/date-part 使用声明 timezone，是否假设时区可追溯 |
| 日期语义 | online、print、issued、created、deposited、indexed、imported_at 分列；discovery event 默认 imported_at→indexed，publication delay 用最早 online/issued，不混写 |
| 新 vs 更新 | `new_works`、`late_arrivals`、`version_updates`、`status_updates`、`unchanged`、`out_of_window`、`review_required` 互斥分类 |
| 延迟补回 | 旧 online/issued 但本窗 indexed/imported 进入 late_arrivals，保留 lag days 和 novelty kind，不冒充新发表 |
| 粒度/边界 | year/month/day 有 interval；模糊区间碰 start/end 进入 review，不猜日；offset 换算后越界的记录不会误推 |
| 去重/版本 | DOI 精确、保守标题模糊 + 作者 + ±1 年、DOI 否决、显式版本组；同源/跨源全部 provenance 和 version signatures 留存 |
| 状态与提醒 | 已读、非 tracked、paused 分别抑制；撤稿/更正是 status update。通知 id 确定性，实际只标 `prepared_not_sent`，不伪造已送达 |
| 漏报与幂等 | source failure、坏记录、缺/错/边界日期、watermark 不连续、paused 均不提交状态；重试不会把临时结果误写为 already seen |
| 计数 | records seen=valid+rejected；identity clusters=各互斥类别之和；collapsed observations、提醒/抑制数均可闭合 |

## 运行流程（结束于 deliverable）

1. 读取 `/input/case.json`、`task.md`、真实来源快照和 organizer-local previous state。保留 `case_id`、完整 `output_contract`、订阅配置和材料时间，**不要读取系统当前时间来补 window**。公开下载不含正式固定 case 数据。
2. 整理 `/app/work/latest_case.json`，设置 `mode:"latest"`、显式窗口、required sources、tracking date policy 和 previous_state。没提供的日期保持缺失。
3. 运行并交付：

```bash
python /skills/weekly-skill/scripts/search_cli.py \
  --case /app/work/latest_case.json --out /app/output
```

输出 `result.json` 和 `next_state.json`。下一窗以本次 `next_state` 为 `previous_state`，并将 start 设为上一窗 committed watermark。
4. 检查 `state_committed`。若为 false，保留旧状态重试；不要用未完整窗口的 next_state 覆盖可信快照。提醒只是本地待交付记录，不存在真实投递回执时不能改成 delivered。

本地合成窗口演示：

```bash
python scripts/search_cli.py --case examples/latest_case.json --out ./out
```

## 最小结构化输入

```json
{
  "case_id": "caller-id",
  "mode": "latest",
  "output_contract": ["case_id", "new_works", "late_arrivals", "version_updates", "next_state"],
  "window": {"start": "2026-03-01T00:00:00Z", "end": "2026-04-01T00:00:00Z", "timezone": "UTC"},
  "tracking_date_fields": ["imported_at", "indexed"],
  "required_sources": ["crossref", "europepmc"],
  "subscription": {"sources": ["crossref", "europepmc"], "read_works": [], "tracked_works": []},
  "previous_state": {"watermark": "2026-03-01T00:00:00Z", "works": [], "notifications": []},
  "sources": {
    "crossref": {"status": "ok", "snapshot_ref": "actual/local/ref", "records": [
      {"id": "cr-1", "version_group": "family-1", "doi": "10.1000/example",
       "title": "Actual retained title", "version": "published",
       "published-online": {"date-parts": [[2026, 3, 4]]},
       "issued": {"date-parts": [[2026, 3, 4]]},
       "created": {"date-time": "2026-03-04T08:00:00Z"},
       "deposited": {"date-time": "2026-03-05T08:00:00Z"},
       "indexed": {"date-time": "2026-03-06T08:00:00Z"}}
    ]},
    "europepmc": {"status": "ok", "records": []}
  }
}
```

可传单个 `tracking_date_field`，或按 source payload 配置。不设策略时依次选 `imported_at`、`indexed`。Europe PMC `firstIndexDate` 映射 indexed，`firstPublicationDate` 与 `pubDate` 映射 issued；Crossref `date-parts`、`date-time`、`timestamp` 均支持。**created、deposited、online、issued 不会静默替代缺失的 indexed**，以免把旧论文当新入库。

### 新文献、更新与延迟判定

- `new_works`：previous snapshot 无该 work family，选定 discovery event 在窗内，online/issued 也在窗内；若 publication date 缺失会明确标 `new_to_snapshot_publication_date_missing`。
- `late_arrivals`：先前不存在于快照、event 在窗内而 online/issued 早于 start；输出 `publication_lag_days`，它是延迟入库，不是否定其“新到快照”价值。
- `version_updates`：已有 work key 出现新 version signature 且 event 在窗内；预印本→正式版需 version_group 才能跨 DOI 归并。
- `status_updates`：已有工作状态改变，或本窗新到 retracted/corrected notice；重放相同状态不重复提醒。
- `unchanged` 与 `out_of_window`：已见相同版本，或 event 不在窗内；不会进入新清单。

`new` 只表示相对提供快照与数据源事件的新，不是全球最先发表或完整性保证。

## previous_state / next_state

`next_state` 包含 watermark、稳定 work keys、DOI/title/year、全部 version records/status/aliases、notifications、read_works、tracked_works。也接受纯 raw old exports 列表作 previous_snapshot 冷导入桥接；其记录按同一身份规则建快照。

仅在以下全部成立时提交：

- required sources 全为 ok/success/complete（成功空窗可以提交，但仍只限该源快照）；
- 没有 rejected records，没有缺/非法/boundary-ambiguous discovery dates；
- start 等于 previous watermark（无时区歧义地比较 instant）；
- subscription 未暂停。

否则 `state_committed=false`，next watermark 保持旧值，works/notifications 不吸收临时发现，以供完整重试。将已 committed next_state 错用于同一窗会识别 overlap/discontinuity 并保持水位，同时抑制已见重复提醒；不会把重叠自动“修正”为连续。

## 提醒与追踪状态

- 每个提醒 id 由 work key + window + kind + version signatures 哈希生成，重跑稳定。
- previous/subscription `read_works` 默认抑制，`notify_read:true` 才可改变；`tracked_works` 非空时只追踪集合内工作。
- paused 输出 suppression 原因且不提交窗口。
- `delivery_log.status=prepared_not_sent`；没有 scheduler、SMTP、RSS、Zotero 写库或 webhook 实现，不能声称定时任务已注册或消息已发送。

## 输出契约与异常

`result.json` 含全部七类列表、`new_items=new_works+late_arrivals`、reminders/suppressed、date interpretations、逐源 coverage、identity merges、missed-reporting risk、count reconciliation、next_state 与 `snapshot_sha256`。

`case_id` 原位保留；output_contract 支持数组、对象键或字符串。引擎字段优先，其他调用方字段直通，未知必需字段为 null + limits。退出码：clean=0、review=3、undetermined=5、usage=2；任何 refusal 都是结构化结果。

## 日期字段参考以及如何落地

实际 Crossref REST work `10.1038/nature12373` 的 retained response 显示：published-online/issued 为 2013-07-31，created 为 2013-07-30，deposited 为 2023-05-18，indexed 为 2026-11-19。这说明 processing timestamps 不能与 publication date 混为一谈。本引擎分别保留各字段；新增发现按声明的 imported/indexed 策略，新旧发表按 online/issued，延迟用二者差值。注意 Crossref indexed 也可能反映再索引，不是永久“首次发现”；稳定订阅应优先保存本地 first_seen/imported_at。
https://api.crossref.org/works/10.1038/nature12373

**Zotero feed/duplicate 机制**启发了“保留库内条目状态、稳定身份、重复条目不 noise push”的实现思路；本包没有声称接入 Zotero 服务，提醒和 read/tracked 状态完全由显式 JSON snapshot 驱动。
https://github.com/zotero/zotero/blob/main/chrome/content/zotero/xpcom/duplicates.js

## Finding 与 refusal 索引

| id | 真实触发 |
|-|-|
| `tracker.window_incomplete` | start/end 缺失、非法或 end<=start，undetermined |
| `tracker.no_sources` | 没有 source snapshots，undetermined |
| `tracker.engine_error` | 增量引擎异常，undetermined |
| `tracker.source_incomplete` | 来源不可用，保持旧水位 |
| `tracker.record_rejected` | 记录不可规范化，保持旧水位 |
| `tracker.date_unresolved` | 缺日期、坏日期或粒度跨窗，保持旧水位 |
| `tracker.window_discontinuity` | start 与 previous watermark 不一致，保持旧水位 |
| `tracker.subscription_paused` | 暂停订阅，不提交窗口 |
| `tracker.empty_source_window` | 成功但零记录的空窗/空源，记录但不必然阻塞 |
| `search.spec_unreadable` | case/corpus/query/index JSON 不可读，exit 5 |
| `search.spec_not_object` | case 不是 JSON 对象，exit 5 |
| `search.engine_error` | 旧引擎异常，exit 5 |
| `search.empty_corpus` | 无可索引记录，exit 5 |
| `search.index_malformed` | index 结构不完整，exit 5 |
| `search.empty_query` | query 无可检索内容，exit 5 |
| `search.doc_skipped` | 旧路径 malformed/duplicate doc 被命名 |

## 旧版兼容

```bash
python scripts/search_cli.py --corpus examples/corpus.json \
  --query-file examples/query.json --out ./out-legacy
```

旧 `YYYY-MM` 字符串检索不知道时区、快照或更新状态，不能替代上面的订阅闭环。

## Requirements 与可选验证

Python 3.9+，仅标准库。`scripts/incremental_tracker.py` 可独立 `run(spec)`；examples 是合成演示，不是正式结果。

```bash
python scripts/bench_latest.py
```

当前 21 个场景：8 条手工跨时区记录的分类/计数、54 天延迟复算、版本/撤稿不冒充新文献、镜像去重、下一快照零重复提醒、已读/暂停、来源失败/缺日期/月粒度边界保持水位、断窗拒收、冷导入/契约/确定性。结果写 `scripts/report_latest.json`。
