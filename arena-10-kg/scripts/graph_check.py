#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图一致性校验：对文献知识图谱的三元组做质量门检查。

检查项（对应本题"抽得准、连得对、对得齐、回得去"四个评分关注点）：
1. 表头与必填列：边表必须含 edge_id, subject, predicate, object,
   source_id, paragraph_id, quote 七列；
2. 悬空边：边的 subject / object 未在节点表中声明（需提供 --nodes）；
3. 重复实体：节点规范名撞车、别名跨节点冲突（同义词/缩写/大小写归一后）；
4. 重复边：同一 (subject, predicate, object) 出现多于一次；
5. 无证据边：source_id / paragraph_id / quote 任一为空；
6. 关系类型合法性：--predicates 给定允许关系表时，表外关系判错；
7. 比较-条件门（v2）：比较类关系（outperforms / more_stable_than /
   compares）的边必须标明比较条件——边表含 condition 列时该列不得为空
   （FAIL）；整表无 condition 列且存在比较边时同样 FAIL（完整管线再执行有向
   schema、condition、实际原文 quote 和 confidence 校验）；
8. 缩写候选表核对（v2，--abbrevs）：阅读时登记的缩写候选（CSV：
   abbr,full_form,source_id,paragraph_id）必须恰好落到一个节点
   （规范名或别名命中）；指向 ≥2 个节点 FAIL，0 个节点 WARN。

用法：
    python graph_check.py --edges /app/output/graph_edges.csv \
        --nodes /app/output/graph_nodes.csv \
        [--predicates /skills/weekly-skill/references/predicates.txt] \
        [--abbrevs /app/work/abbrev_candidates.csv] \
        [--report /app/work/graph_check_report.md]

退出码：0 = 全部通过（可有 WARN）；1 = 存在错误项（明细见输出与报告）。
退出码 1 仅表示存在建议修复项；无论退出码如何，都应照常交付 result.json
并在 uncertainty 中记录未修复项——本脚本不充当交付门禁。
约束：stdlib-only；输入只读；utf-8-sig 读文件；不依赖 CWD。
"""

import argparse
import csv
import os
import sys
import unicodedata

EDGE_COLUMNS = ["edge_id", "subject", "predicate", "object",
                "source_id", "paragraph_id", "quote"]
NODE_COLUMNS = ["node_id", "label", "type", "aliases"]


def norm(text):
    """归一化实体名：NFKC + 去首尾空白 + 压缩内部空白 + 小写折叠。"""
    t = unicodedata.normalize("NFKC", text or "")
    return " ".join(t.split()).casefold()


def read_csv_rows(path, required_cols, tag, errors):
    rows, header = [], []
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames or []
            missing = [c for c in required_cols if c not in header]
            if missing:
                errors.append("[%s] 表头缺少列：%s（实际表头：%s）"
                              % (tag, ", ".join(missing), ", ".join(header)))
                return rows, header
            for i, row in enumerate(reader, 2):  # 第 1 行是表头
                row["_line"] = i
                rows.append(row)
    except FileNotFoundError:
        errors.append("[%s] 文件不存在：%s" % (tag, path))
    except OSError as exc:
        errors.append("[%s] 读取失败：%s（%s）" % (tag, path, exc))
    return rows, header


COMPARATIVE_PREDICATES = {"outperforms", "more_stable_than", "compares"}


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="文献知识图谱三元组质量门：悬空边/重复实体/无证据边检测")
    parser.add_argument("--edges", required=True, help="三元组边表 CSV")
    parser.add_argument("--nodes", default=None, help="节点表 CSV（强烈建议提供）")
    parser.add_argument("--predicates", default=None,
                        help="允许的关系类型清单（每行一个，可选）")
    parser.add_argument("--abbrevs", default=None,
                        help="缩写候选表 CSV（abbr,full_form,source_id,paragraph_id，可选）")
    parser.add_argument("--report", default=None, help="Markdown 报告输出路径（可选）")
    args = parser.parse_args(argv)

    errors, warnings, notes = [], [], []

    # ---------- 读边表 ----------
    edges, edge_header = read_csv_rows(os.path.abspath(args.edges), EDGE_COLUMNS,
                                       "边表", errors)
    # ---------- 读节点表 ----------
    nodes = []
    if args.nodes:
        nodes, _ = read_csv_rows(os.path.abspath(args.nodes), NODE_COLUMNS,
                                 "节点表", errors)
    else:
        warnings.append("未提供 --nodes，跳过悬空边校验；"
                        "强烈建议生成节点表后复检。")

    node_ids, label_owner, alias_owner = set(), {}, {}
    for n in nodes:
        nid = (n.get("node_id") or "").strip()
        label = (n.get("label") or "").strip()
        ntype = (n.get("type") or "").strip()
        if not nid:
            errors.append("[节点表] 第 %d 行 node_id 为空" % n["_line"])
            continue
        if nid in node_ids:
            errors.append("[节点表] node_id 重复：%s（第 %d 行）"
                          % (nid, n["_line"]))
        node_ids.add(nid)
        if not label:
            errors.append("[节点表] %s 的 label 为空" % nid)
        if not ntype:
            errors.append("[节点表] %s 的 type 为空" % nid)
        key = norm(label)
        if key:
            if key in label_owner:
                errors.append("[重复实体] 规范名撞车：'%s' 同时属于 %s 与 %s，"
                              "应合并或给出不得合并的书面依据"
                              % (label, label_owner[key], nid))
            elif key in alias_owner:
                errors.append("[重复实体] %s 的规范名 '%s' 与 %s 的别名冲突，"
                              "疑似同一实体重复建点"
                              % (nid, label, alias_owner[key]))
            else:
                label_owner[key] = nid
        aliases = [a.strip() for a in (n.get("aliases") or "").split(";")
                   if a.strip()]
        for a in aliases:
            ak = norm(a)
            if not ak:
                continue
            if ak in label_owner and label_owner[ak] != nid:
                errors.append("[重复实体] %s 的别名 '%s' 与 %s 的规范名冲突"
                              % (nid, a, label_owner[ak]))
            elif ak in alias_owner and alias_owner[ak] != nid:
                errors.append("[重复实体] 别名 '%s' 同时登记在 %s 与 %s 下"
                              % (a, alias_owner[ak], nid))
            else:
                alias_owner[ak] = nid

    # ---------- 允许关系表 ----------
    allowed_pred = None
    if args.predicates:
        try:
            with open(os.path.abspath(args.predicates), "r",
                      encoding="utf-8-sig") as f:
                allowed_pred = {norm(line) for line in f if line.strip()
                                and not line.startswith("#")}
        except OSError as exc:
            errors.append("[关系表] 读取失败：%s（%s）" % (args.predicates, exc))

    # ---------- 逐边校验 ----------
    seen_edges = {}
    for e in edges:
        eid = (e.get("edge_id") or "").strip() or "第%d行" % e["_line"]
        subj = (e.get("subject") or "").strip()
        pred = (e.get("predicate") or "").strip()
        obj = (e.get("object") or "").strip()
        if not subj or not pred or not obj:
            errors.append("[边表] %s 的 subject/predicate/object 有空值" % eid)
            continue
        # 无证据边
        missing_ev = [c for c in ("source_id", "paragraph_id", "quote")
                      if not (e.get(c) or "").strip()]
        if missing_ev:
            errors.append("[无证据边] %s 缺少证据字段：%s"
                          % (eid, ", ".join(missing_ev)))
        # 悬空边
        if args.nodes:
            for role, val in (("subject", subj), ("object", obj)):
                if val not in node_ids:
                    errors.append("[悬空边] %s 的 %s='%s' 未在节点表中声明"
                                  % (eid, role, val))
        # 重复边
        key = (norm(subj), norm(pred), norm(obj))
        if key in seen_edges:
            errors.append("[重复边] %s 与 %s 均为 (%s, %s, %s)，"
                          "应合并为一条边并并列两组证据"
                          % (eid, seen_edges[key], subj, pred, obj))
        else:
            seen_edges[key] = eid
        # 关系类型合法性
        if allowed_pred is not None and norm(pred) not in allowed_pred:
            errors.append("[关系表] %s 的关系 '%s' 不在允许清单内，"
                          "请改用标准关系或先扩充 schema" % (eid, pred))
        # 比较-条件门：比较类关系必须标明比较条件
        if norm(pred) in COMPARATIVE_PREDICATES:
            if "condition" in edge_header:
                if not (e.get("condition") or "").strip():
                    errors.append("[比较-条件门] %s 是比较类关系（%s）但 condition 为空："
                                  "涉及对比的论断必须标明比较条件"
                                  "（温度/组成/测试协议等），否则结论不可比" % (eid, pred))
            # 整表无 condition 列的情形在循环外统一 WARN

    if edges and "condition" not in edge_header:
        comparative = [ (e.get("edge_id") or "?").strip() for e in edges
                        if norm((e.get("predicate") or "").strip())
                        in COMPARATIVE_PREDICATES ]
        if comparative:
            errors.append("边表无 condition 列，但存在比较类边 %s："
                          "比较-条件门不满足；请标明条件后再成图，不能把信息缺失降级成普通警告"
                          % ", ".join(comparative))

    # ---------- 缩写候选表核对（--abbrevs）----------
    if args.abbrevs:
        abbr_rows, _ = read_csv_rows(os.path.abspath(args.abbrevs),
                                     ["abbr", "full_form"], "缩写候选表", errors)
        for r in abbr_rows:
            ab = (r.get("abbr") or "").strip()
            ff = (r.get("full_form") or "").strip()
            if not ab:
                continue
            owners = set()
            for key in (norm(ab), norm(ff)):
                if not key:
                    continue
                if key in label_owner:
                    owners.add(label_owner[key])
                if key in alias_owner:
                    owners.add(alias_owner[key])
            loc = "%s:%s" % ((r.get("source_id") or "?").strip(),
                             (r.get("paragraph_id") or "?").strip())
            if len(owners) > 1:
                errors.append("[缩写候选] %r/%r（%s）命中多个节点 %s："
                              "缩写归并冲突，须先裁决合并或拆分"
                              % (ab, ff, loc, ", ".join(sorted(owners))))
            elif not owners:
                warnings.append("[缩写候选] %r/%r（%s）未落到任何节点："
                                "若是实体应建点或并入别名；若非实体请在名册注明"
                                % (ab, ff, loc))

    notes.append("边数 %d；节点数 %d；唯一 (s,p,o) 组合 %d"
                 % (len(edges), len(nodes), len(seen_edges)))

    # ---------- 汇总输出 ----------
    print("=" * 60)
    print("图一致性校验报告")
    print("=" * 60)
    for n in notes:
        print("[INFO] %s" % n)
    for w in warnings:
        print("[WARN] %s" % w)
    if errors:
        for i, e in enumerate(errors, 1):
            print("[FAIL %d] %s" % (i, e))
        print("结果：未通过（%d 个错误，%d 个警告）" % (len(errors), len(warnings)))
    else:
        print("[PASS] 悬空边 / 重复实体 / 无证据边 / 重复边 / 关系合法性 全部通过")
        print("结果：通过（0 个错误，%d 个警告）" % len(warnings))

    if args.report:
        rep = os.path.abspath(args.report)
        os.makedirs(os.path.dirname(rep) or ".", exist_ok=True)
        with open(rep, "w", encoding="utf-8") as f:
            f.write("# 图一致性校验报告\n\n")
            f.write("边表：`%s`\n\n" % args.edges)
            f.write("节点表：`%s`\n\n" % (args.nodes or "（未提供）"))
            f.write("## 统计\n\n")
            for n in notes:
                f.write("- %s\n" % n)
            f.write("\n## 错误（%d）\n\n" % len(errors))
            for e in errors:
                f.write("- %s\n" % e)
            f.write("\n## 警告（%d）\n\n" % len(warnings))
            for w in warnings:
                f.write("- %s\n" % w)
        print("[OK] 报告已写入 %s" % rep)

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
