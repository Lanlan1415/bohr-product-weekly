# Bohr 产品周赛 · 第四期参赛作品集

本仓库收录参加玻尔科研产品周赛（product weekly）第四期的全部 Skill 作品包。
每个子目录是一个独立可提交的 Skill：SKILL.md（用途/调用方式/输入输出/异常处理）、
scripts/（可运行引擎与回归 bench）、examples/（最小调用示例，输出标注"示例"）、
GITHUB_URL.txt（指回本仓库的定位文件）。

## 包一览

| 目录 | 对应赛题（第四期） |
|-|-|
| p02-figure-parse/ | 产品周赛第四期参赛作品 |
| p05-evidence-writing/ | 产品周赛第四期参赛作品 |
| p10-clean/ | 产品周赛第四期参赛作品 |
| p101-compare-docs/ | 产品周赛第四期参赛作品 |
| p105-conclusion-extract/ | 产品周赛第四期参赛作品 |
| p106-claim-verify/ | 产品周赛第四期参赛作品 |
| p107-formula/ | 产品周赛第四期参赛作品 |
| p108-reproduce/ | 产品周赛第四期参赛作品 |
| p11-qa/ | 产品周赛第四期参赛作品 |
| p110-results-discussion/ | 产品周赛第四期参赛作品 |
| p111-paper-draft/ | 产品周赛第四期参赛作品 |
| p115-structure/ | 产品周赛第四期参赛作品 |
| p115b-opendoc/ | 产品周赛第四期参赛作品 |
| p117-dissemination/ | 产品周赛第四期参赛作品 |
| p119-proposal/ | 产品周赛第四期参赛作品 |
| p12-translation/ | 产品周赛第四期参赛作品 |
| p120-longdoc/ | 产品周赛第四期参赛作品 |
| p124-mindmap/ | 产品周赛第四期参赛作品 |
| p12b-format-template/ | 产品周赛第四期参赛作品 |
| p17-review-response/ | 产品周赛第四期参赛作品 |
| p25-schematic/ | 产品周赛第四期参赛作品 |
| p26-source-chart/ | 产品周赛第四期参赛作品 |
| p27-pathway/ | 产品周赛第四期参赛作品 |
| p28-apparatus/ | 产品周赛第四期参赛作品 |
| p29-graphical-abstract/ | Graphical Abstract（图形摘要）（graphical-abstract-7030fff2） |
| p30-paper-to-deck/ | 产品周赛第四期参赛作品 |
| p31-deck-edit/ | 产品周赛第四期参赛作品 |
| p32-talk-org/ | 产品周赛第四期参赛作品 |
| p33-template-fit/ | 产品周赛第四期参赛作品 |
| p34-data-quality/ | 产品周赛第四期参赛作品 |
| p40-reading-master/ | 产品周赛第四期参赛作品 |
| p41-writing-master/ | 产品周赛第四期参赛作品 |
| p42-graphics-master/ | Graphical Abstract（图形摘要）（graphical-abstract-7030fff2） |
| p43-ppt-master/ | 产品周赛第四期参赛作品 |
| p44-web-translate/ | 产品周赛第四期参赛作品 |
| p45-reading-annotate/ | 产品周赛第四期参赛作品 |
| p46-data-viz/ | 产品周赛第四期参赛作品 |
| p47-stats-interpretation/ | 产品周赛第四期参赛作品 |
| p48-result-interpretation/ | 产品周赛第四期参赛作品 |
| p49-paper-quality-audit/ | 产品周赛第四期参赛作品 |
| p50-method-stats-audit/ | 产品周赛第四期参赛作品 |
| p51-compliance-audit/ | 产品周赛第四期参赛作品 |
| p52-doc-classify/ | 产品周赛第四期参赛作品 |
| p53-library-mgmt/ | 产品周赛第四期参赛作品 |
| p54-file-search/ | 产品周赛第四期参赛作品 |
| p55-search-coverage/ | 产品周赛第四期参赛作品 |
| p56-search-latest/ | 产品周赛第四期参赛作品 |
| p57-search-systematic/ | 产品周赛第四期参赛作品 |
| p58-search-citation/ | 产品周赛第四期参赛作品 |
| p59-search-patent/ | 产品周赛第四期参赛作品 |
| p60-search-quality/ | 产品周赛第四期参赛作品 |
| p61-search-multi-db/ | 产品周赛第四期参赛作品 |
| p62-search-crosslang/ | 产品周赛第四期参赛作品 |
| p63-search-question/ | 产品周赛第四期参赛作品 |
| p64-review-generate/ | 产品周赛第四期参赛作品 |
| p65-search-filter-rank/ | 产品周赛第四期参赛作品 |
| p66-search-academic/ | 产品周赛第四期参赛作品 |
| p67-search-systematic-review/ | 产品周赛第四期参赛作品 |
| p68-kb-qa/ | 产品周赛第四期参赛作品 |
| p69-trend-analysis/ | 产品周赛第四期参赛作品 |
| p70-topic-evaluation/ | 产品周赛第四期参赛作品 |
| p71-experiment-optimize/ | 产品周赛第四期参赛作品 |
| p72-experiment-feasibility/ | 产品周赛第四期参赛作品 |
| p73-db-query/ | 产品周赛第四期参赛作品 |
| pb-reading-bench/ | 产品周赛第四期参赛作品 |
| pb-writing-bench/ | 产品周赛第四期参赛作品 |
| pc-reading-client/ | 产品周赛第四期参赛作品 |
| pc-writing-client/ | 产品周赛第四期参赛作品 |

## 复跑验证

每个包自带回归 bench（scripts/bench_*.py），可独立复跑，例如：

```
python -I -X utf8 p41-writing-master/scripts/bench_sections.py
python -I -X utf8 p48-result-interpretation/scripts/bench_interp.py
```

各包 SKILL.md 的 Verification 节写明对应命令与本机通过记录（clean 基线必须零发现）。

## 依赖

- 写作/审查/检索/资料族：纯 Python 标准库（3.9+，3.14 实测）
- 绘图族（p25/p26/p27/p28/p29/p42/p46）：matplotlib
- PPT 族（p30/p31/p33）：python-pptx + Pillow（可选，缺失时引擎诚实降级并说明）

## 运行时契约（统一）

每个案例运行时读 /input/case.json 与 task.md；result.json 保留 case.json 的
output_contract 全部字段与 case_id；材料缺失/不可判断/运行失败分别落盘说明，
拒绝路径 exit 5 + result.json，永不裸抛 traceback。
