#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""graphml_roundtrip.py —— GraphML 导出与回导一致性验证（阅读15）。

交付图谱时，GraphML 是常用的图工具交换格式。本脚本做两件事：
1. 默认模式（导出+回导）：把 graph_nodes.csv / graph_edges.csv 写成
   GraphML（stdlib xml.etree），立即重新解析该文件，核对回导出的
   节点集、边集与全部属性**与 CSV 逐项一致**——证明导出无损、可回导；
2. --verify-only 模式：不覆盖写，只把既有 GraphML 与 CSV 比对
   （用于事后检测 GraphML 是否被手工改动）。

GraphML 结构：每个节点/边的属性用 <data key=...> 携带；key 在 <key>
元素中声明（node: label/type/aliases；edge: predicate/source_id/
paragraph_id/quote/evidence_strength 及 CSV 里存在的可选列
value/unit/condition）。

用法：
    python3 /skills/weekly-skill/scripts/graphml_roundtrip.py \
        --nodes /app/output/graph_nodes.csv \
        --edges /app/output/graph_edges.csv \
        --graphml /app/output/graph.graphml [--verify-only] \
        [--report /app/work/graphml_roundtrip_report.md]

退出码：0 = 一致（GraphML 可回导）；1 = 不一致或读写失败。
退出码 1 仅表示存在建议修复项；无论退出码如何，都应照常交付 result.json
并在 uncertainty 中记录未修复项——本脚本不充当交付门禁。
约束：stdlib-only；utf-8-sig；不依赖 CWD；不联网。
"""

import argparse
import csv
import os
import sys
import xml.etree.ElementTree as ET

NODE_KEYS = ["label", "type", "aliases"]
EDGE_KEYS = ["predicate", "source_id", "paragraph_id", "quote",
             "evidence_strength", "value", "unit", "condition"]
GML_NS = "http://graphml.graphdrawing.org/xmlns"


def read_csv(path, required, tag, errors):
    rows, header = [], []
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames or []
            missing = [c for c in required if c not in header]
            if missing:
                errors.append("[%s] 表头缺少列：%s" % (tag, ", ".join(missing)))
                return rows, header
            rows = list(reader)
    except OSError as exc:
        errors.append("[%s] 读取失败：%s（%s）" % (tag, path, exc))
    return rows, header


def export_graphml(nodes, edges, edge_header, path):
    """写 GraphML；返回使用的边属性列（用于回导比对）。"""
    edge_attrs = [k for k in EDGE_KEYS if k in edge_header]
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<graphml xmlns="%s">' % GML_NS]
    for k in NODE_KEYS:
        lines.append('  <key id="n_%s" for="node" attr.name="%s" attr.type="string"/>'
                     % (k, k))
    for k in edge_attrs:
        lines.append('  <key id="e_%s" for="edge" attr.name="%s" attr.type="string"/>'
                     % (k, k))
    lines.append('  <graph id="G" edgedefault="directed">')
    esc = lambda s: (s or "").replace("&", "&amp;").replace("<", "&lt;") \
        .replace(">", "&gt;").replace('"', "&quot;")
    for n in nodes:
        lines.append('    <node id="%s">' % esc(n.get("node_id")))
        for k in NODE_KEYS:
            lines.append('      <data key="n_%s">%s</data>'
                         % (k, esc(n.get(k))))
        lines.append('    </node>')
    for e in edges:
        lines.append('    <edge id="%s" source="%s" target="%s">'
                     % (esc(e.get("edge_id")), esc(e.get("subject")),
                        esc(e.get("object"))))
        for k in edge_attrs:
            lines.append('      <data key="e_%s">%s</data>'
                         % (k, esc(e.get(k))))
        lines.append('    </edge>')
    lines.append('  </graph>')
    lines.append('</graphml>')
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return edge_attrs


def import_graphml(path):
    """解析 GraphML；返回 (nodes_dict, edges_dict)。"""
    tree = ET.parse(path)
    root = tree.getroot()
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"
    nodes, edges = {}, {}
    for node in root.iter(ns + "node"):
        nid = node.get("id")
        data = {d.get("key")[2:]: (d.text or "")
                for d in node.findall(ns + "data")
                if d.get("key", "").startswith("n_")}
        data["node_id"] = nid
        nodes[nid] = data
    for edge in root.iter(ns + "edge"):
        eid = edge.get("id")
        data = {d.get("key")[2:]: (d.text or "")
                for d in edge.findall(ns + "data")
                if d.get("key", "").startswith("e_")}
        data.update({"edge_id": eid, "subject": edge.get("source"),
                     "object": edge.get("target")})
        edges[eid] = data
    return nodes, edges


def diff_records(tag, want, got, keys, errors):
    """逐记录比对 CSV 行与回导记录；keys 为比对字段。"""
    for rid, w in want.items():
        if rid not in got:
            errors.append("[%s] 回导缺失记录：%s" % (tag, rid))
            continue
        g = got[rid]
        for k in keys:
            if (w.get(k) or "") != (g.get(k) or ""):
                errors.append("[%s] %s 的字段 %r 不一致：CSV=%r ≠ GraphML=%r"
                              % (tag, rid, k, w.get(k), g.get(k)))
    for rid in got:
        if rid not in want:
            errors.append("[%s] GraphML 多出记录：%s" % (tag, rid))


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="GraphML 导出 + 回导一致性验证")
    parser.add_argument("--nodes", required=True)
    parser.add_argument("--edges", required=True)
    parser.add_argument("--graphml", required=True)
    parser.add_argument("--verify-only", action="store_true",
                        help="不覆盖写，只比对既有 GraphML 与 CSV")
    parser.add_argument("--report", default=None)
    args = parser.parse_args(argv)

    errors, notes = [], []
    nodes, _ = read_csv(os.path.abspath(args.nodes), ["node_id", "label", "type"],
                        "节点表", errors)
    edges, edge_header = read_csv(os.path.abspath(args.edges),
                                  ["edge_id", "subject", "predicate", "object"],
                                  "边表", errors)
    if errors:
        for e in errors:
            print("[FAIL] %s" % e)
        return 1

    gml = os.path.abspath(args.graphml)
    edge_attrs = [k for k in EDGE_KEYS if k in edge_header]
    if not args.verify_only:
        try:
            export_graphml(nodes, edges, edge_header, gml)
            notes.append("GraphML 已导出：%s（节点 %d，边 %d，边属性 %s）"
                         % (gml, len(nodes), len(edges), ",".join(edge_attrs)))
        except OSError as exc:
            print("[FAIL] GraphML 写入失败：%s" % exc)
            return 1
    elif not os.path.isfile(gml):
        print("[FAIL] --verify-only 但 GraphML 不存在：%s" % gml)
        return 1

    try:
        g_nodes, g_edges = import_graphml(gml)
    except (ET.ParseError, OSError) as exc:
        print("[FAIL] GraphML 回导解析失败：%s" % exc)
        return 1

    diff_records("节点", {n["node_id"]: n for n in nodes}, g_nodes,
                 ["node_id", "label", "type", "aliases"], errors)
    diff_records("边", {e["edge_id"]: e for e in edges}, g_edges,
                 ["edge_id", "subject", "object"] + edge_attrs, errors)
    notes.append("回导比对字段：节点 4 个；边 %d 个" % (3 + len(edge_attrs)))

    print("=" * 60)
    print("GraphML 往返一致性验证")
    print("=" * 60)
    for n in notes:
        print("[INFO] %s" % n)
    if errors:
        for e in errors:
            print("[FAIL] %s" % e)
        print("结果：未通过（%d 处不一致）" % len(errors))
    else:
        print("[PASS] CSV → GraphML → 回导 完全一致（可回导）")
        print("结果：通过")

    if args.report:
        rep = os.path.abspath(args.report)
        os.makedirs(os.path.dirname(rep) or ".", exist_ok=True)
        with open(rep, "w", encoding="utf-8") as f:
            f.write("# GraphML 往返一致性报告\n\n")
            for n in notes:
                f.write("- %s\n" % n)
            f.write("\n## 不一致（%d）\n\n" % len(errors))
            for e in errors:
                f.write("- %s\n" % e)
        print("[OK] 报告已写入 %s" % rep)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
