# 交付物骨架（参考文献与引用管理）

/app/output/ 下的标准布局（文件名可按契约字段名调整，但 result.json 中如实指向）：

```
/app/output/
  manuscript_revised.md     # 修订稿（可编辑）：正文引用已定位/重排 + 同步参考文献
  citation_check_report.md  # citation_check.py 输出：缺引/多引/断号/错位/字段 lint
  dedupe_report.md          # dedupe_refs.py 输出 + 每对候选的合并/保留决策
  evidence_map.md           # S1..Sn 文献库登记 + 论断—引用映射 + 修改记录 + 待确认
  result.json               # 契约字段透传 + 诚实 status
```

## manuscript_revised.md 骨架

```markdown
# <原稿标题>（引用整理修订版）

<正文，引用标记已按 method_rules §1-3 处理>

## 参考文献

[1] <按目标规范著录；缺失字段显式标注「[缺: 字段名]」>
[2] ...
```

## 写作要求

- 修订稿保持原稿结构与文字，只改引用相关部分；其他改动须进 change_log 说明理由。
- 文献表与正文编号严格对应（citation_check.py ERROR=0）。
- 被合并条目的原编号去向写入 dedupe_report.md，不静默消失。
- 若任务要求 docx：先生成 md，用 office-renderer 转 docx，并渲染 PDF 预览一并交付。
